# coding=utf-8
"""
/***************************************************************************
treemap plugin
                                 A QGIS plugin
 Projette des points sur une ligne/bordure de polygone à la distance la plus courte: "ClosestPoint"
                              -------------------
        begin                : 2025-09-07
        copyright            : (C) 2025 by Jean-Christophe Baudin  
        email                : jean-christophe.baudin@ymail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# (c) JC BAUDIN 2025 09 07
 
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QTextEdit, QPushButton, QMessageBox,
    QScrollArea, QTextBrowser, QLineEdit, QComboBox, QHBoxLayout, QLabel, QFileDialog,
    QAction, QCheckBox, QGroupBox, QGridLayout
)
from PyQt5.QtCore import QUrl, QVariant
from PyQt5.QtGui import QColor, QIcon
from qgis.core import QgsVectorLayer, QgsProject, QgsField, QgsFields, QgsFeature, QgsGeometry, QgsPointXY
import os
import tempfile
import shutil
import math
import statistics
from collections import defaultdict
import sys

# Augmenter la limite de récursion temporairement (optionnel, à utiliser avec prudence)
sys.setrecursionlimit(2000)

def compute_treemap_rects(sizes, outer_rect, horizontal=True, depth=0, max_depth=100):
    """
    Calcule les rectangles d'un treemap de manière récursive avec une limite de profondeur.
    Ajoute des vérifications pour éviter les récursions infinies.
    """
    # Conditions d'arrêt
    if not sizes or depth >= max_depth:
        return []
    total = sum(sizes)
    if total <= 0:
        return []
    if len(sizes) == 1:
        return [outer_rect]
    
    # Éviter les divisions si les tailles sont trop petites
    if total < 1e-6:  # Seuil pour éviter les erreurs avec des surfaces trop petites
        return []

    x0, y0, x1, y1 = outer_rect
    width = x1 - x0
    height = y1 - y0
    
    # Vérifier si le rectangle est trop petit pour être divisé
    if width < 1e-6 or height < 1e-6:
        return []

    half = total / 2.0
    acc = 0.0
    split_idx = 0
    for i, a in enumerate(sizes):
        acc += a
        if acc >= half:
            split_idx = i + 1
            break
    if split_idx == 0:
        split_idx = 1

    left_sizes = sizes[:split_idx]
    right_sizes = sizes[split_idx:]

    if horizontal:
        left_width = width * (sum(left_sizes) / total) if total > 0 else 0
        if left_width < 1e-6:  # Éviter les rectangles trop petits
            return []
        left_rect = (x0, y0, x0 + left_width, y1)
        right_rect = (x0 + left_width, y0, x1, y1)
    else:
        left_height = height * (sum(left_sizes) / total) if total > 0 else 0
        if left_height < 1e-6:  # Éviter les rectangles trop petits
            return []
        left_rect = (x0, y0, x1, y0 + left_height)
        right_rect = (x0, y0 + left_height, x1, y1)

    # Appels récursifs avec profondeur incrémentée
    left_geo = compute_treemap_rects(left_sizes, left_rect, not horizontal, depth + 1, max_depth)
    right_geo = compute_treemap_rects(right_sizes, right_rect, not horizontal, depth + 1, max_depth)
    return left_geo + right_geo

class TreemapDialog(QDialog):
    def __init__(self, parent=None, iface=None):
        super(TreemapDialog, self).__init__(parent)
        self.iface = iface
        self.setWindowTitle("Treemap polygons layer")
        self.setMinimumWidth(800)
        self.temp_dir = None
        self.layer = None
        self.treemap_layer = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.tabs = QTabWidget()
        self.setup_instructions_tab()
        self.setup_analysis_tab()
        self.tabs.addTab(self.instructions_tab, "Instructions")
        self.tabs.addTab(self.analysis_tab, "Processing")
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def setup_instructions_tab(self):
        layout = QVBoxLayout()
        self.instructions_text = QTextEdit()
        self.instructions_text.setReadOnly(True)
        instructions = """
        <h2>Treemap Shapefile</h2>
        <h3>What does it do :</h3>
        <p>It generates a treemap layer from a polygon layer based on a single categorical attribute.</p>
        <p>It calculates the total areas in m2, km2, hectares.</p>
        <p>REMARK: all values are rounded to two decimal places.</p>
        <h3>Data required :</h3>
        <p>A polygon or multipolygons layer visible in QGIS.</p>
        <p>An attribute table containing an attribute field for the categories.</p>
        <h3>Usage :</h3>
        <ol>
            <li>Select the polygon layer.</li>
            <li>Choose the attribute field representing the categories.</li>
            <li>Click the "Generate Treemap" button. </li>
        </ol>
        <h3>Usage Limits:</h3>
        <p>To avoid performance issues and recursion errors, the plugin limits the number of categories:</p>
        <ul>
            <li>Maximum 50 unique categories for the selected attribute.</li>
        </ul>
        <p>If this limit is exceeded, an error message will be displayed, and the treemap generation will be aborted. Consider simplifying your data or using fewer categories.</p>
        """
        self.instructions_text.setHtml(instructions)
        layout.addWidget(self.instructions_text)
        self.instructions_tab = QWidget()
        self.instructions_tab.setLayout(layout)

    def setup_analysis_tab(self):
        layout = QVBoxLayout()

        # Sélection de la couche de polygones
        polygon_layout = QHBoxLayout()
        self.polygon_label = QLabel("Select a polygon/multipolygon layer :")
        self.polygon_combo_box = QComboBox()
        self.load_polygon_layers()
        self.show_fields_button = QPushButton("Show attribute fields")
        polygon_layout.addWidget(self.polygon_label)
        polygon_layout.addWidget(self.polygon_combo_box)
        polygon_layout.addWidget(self.show_fields_button)
        layout.addLayout(polygon_layout)

        # Champ attributaire 1 (seul attribut)
        field1_layout = QHBoxLayout()
        self.field1_label = QLabel("Qualitative/categorical variable :")
        self.field1_combo_box = QComboBox()
        field1_layout.addWidget(self.field1_label)
        field1_layout.addWidget(self.field1_combo_box)
        layout.addLayout(field1_layout)

        # Positionnement du treemap
        position_label = QLabel("Select treemap layer location :")
        layout.addWidget(position_label)

        # Layout pour le rectangle et les cases à cocher
        position_group_layout = QGridLayout()

        # Rectangle "layer extent" centré
        self.extent_group = QGroupBox()
        extent_inner_layout = QVBoxLayout()
        self.extent_label = QLabel("layer extent")
        extent_inner_layout.addWidget(self.extent_label)
        self.extent_group.setLayout(extent_inner_layout)
        position_group_layout.addWidget(self.extent_group, 1, 1)

        # Cases à cocher autour du rectangle
        self.top_checkbox = QCheckBox("Up")
        self.bottom_checkbox = QCheckBox("Down")
        self.left_checkbox = QCheckBox("Left")
        self.right_checkbox = QCheckBox("Right")

        self.top_checkbox.stateChanged.connect(self.on_checkbox_changed)
        self.bottom_checkbox.stateChanged.connect(self.on_checkbox_changed)
        self.left_checkbox.stateChanged.connect(self.on_checkbox_changed)
        self.right_checkbox.stateChanged.connect(self.on_checkbox_changed)

        position_group_layout.addWidget(self.top_checkbox, 0, 1)
        position_group_layout.addWidget(self.bottom_checkbox, 2, 1)
        position_group_layout.addWidget(self.left_checkbox, 1, 0)
        position_group_layout.addWidget(self.right_checkbox, 1, 2)

        layout.addLayout(position_group_layout)

        # Bouton de génération
        self.treemap_button = QPushButton("Generate the Treemap")
        self.treemap_button.clicked.connect(self.create_treemap_layer)
        layout.addWidget(self.treemap_button)

        self.analysis_tab = QWidget()
        self.analysis_tab.setLayout(layout)

        # Connexions
        self.polygon_combo_box.currentIndexChanged.connect(self.on_polygon_layer_changed)
        self.show_fields_button.clicked.connect(self.load_attribute_fields)

    def on_checkbox_changed(self, state):
        sender = self.sender()
        if state == 2:  # Checked
            if sender == self.top_checkbox:
                self.bottom_checkbox.setChecked(False)
                self.left_checkbox.setChecked(False)
                self.right_checkbox.setChecked(False)
            elif sender == self.bottom_checkbox:
                self.top_checkbox.setChecked(False)
                self.left_checkbox.setChecked(False)
                self.right_checkbox.setChecked(False)
            elif sender == self.left_checkbox:
                self.top_checkbox.setChecked(False)
                self.bottom_checkbox.setChecked(False)
                self.right_checkbox.setChecked(False)
            elif sender == self.right_checkbox:
                self.top_checkbox.setChecked(False)
                self.bottom_checkbox.setChecked(False)
                self.left_checkbox.setChecked(False)

    def load_polygon_layers(self):
        self.polygon_combo_box.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == layer.VectorLayer and layer.geometryType() in [2, 5]:  # Polygon/MultiPolygon
                self.polygon_combo_box.addItem(layer.name(), layer)

    def on_polygon_layer_changed(self):
        self.field1_combo_box.clear()

    def load_attribute_fields(self):
        layer = self.polygon_combo_box.currentData()
        if layer is None:
            QMessageBox.warning(self, "Error", "Please select a polygon layer.")
            return
        self.layer = layer
        fields = [field.name() for field in self.layer.fields()]
        self.field1_combo_box.clear()
        self.field1_combo_box.addItems(fields)

    def compute_statistics(self):
        layer = self.polygon_combo_box.currentData()
        if layer is None:
            QMessageBox.warning(self, "Error", "Please select a polygon layer.")
            return False
        field1_name = self.field1_combo_box.currentText()
        if not field1_name:
            QMessageBox.warning(self, "Error", "Please select the attribute field.")
            return False
        self.layer = layer
        self.count_dict = {}
        self.surface_dict_m2 = {}
        for feature in self.layer.getFeatures():
            cat1 = feature.attribute(field1_name)
            if cat1:
                if cat1 not in self.count_dict:
                    self.count_dict[cat1] = 0
                    self.surface_dict_m2[cat1] = []
                self.count_dict[cat1] += 1
                area_m2 = feature.geometry().area()
                self.surface_dict_m2[cat1].append(area_m2)
        if not self.count_dict:
            QMessageBox.critical(self, "Error", "No valid data found in the layer.")
            return False
        
        # Vérification des limites de catégories
        MAX_CATEGORIES = 50
        
        num_categories = len(self.count_dict)
        if num_categories > MAX_CATEGORIES:
            QMessageBox.warning(self, "Category Limit Exceeded", f"Too many unique categories ({num_categories} > {MAX_CATEGORIES}). Please reduce the number of unique values in the attribute field.")
            return False
        
        return True

    def create_treemap_layer(self):
        if not self.compute_statistics():
            return
        try:
            field1_name = self.field1_combo_box.currentText()
            layer_name = self.polygon_combo_box.currentText()  # Nom de la couche initiale

            # Calcul des tailles totales par catégorie
            sizes = {}
            for cat, surfaces in self.surface_dict_m2.items():
                total_m2 = sum(surfaces)
                sizes[cat] = total_m2

            # Tri des catégories
            areas_sorted = sorted(sizes.items(), key=lambda x: x[1], reverse=True)
            cats = [k for k, v in areas_sorted]
            sizes_list = [v for k, v in areas_sorted]
            total = sum(sizes_list)

            # Calcul des rectangles
            aspect = 1.6
            h = math.sqrt(total / aspect)
            w = aspect * h
            outer_rect = (0.0, 0.0, w, h)
            rects = compute_treemap_rects(sizes_list, outer_rect, max_depth=50)

            # Positionnement
            ext = self.layer.extent()
            xmin_orig = ext.xMinimum()
            ymin_orig = ext.yMinimum()
            xmax_orig = ext.xMaximum()
            ymax_orig = ext.yMaximum()
            height_orig = ymax_orig - ymin_orig
            width_orig = xmax_orig - xmin_orig
            gap = height_orig * 0.05
            gap_2 = width_orig * 0.05
            
            if self.top_checkbox.isChecked():
                y_shift = ymax_orig + gap
                x_shift = (xmin_orig + xmax_orig) / 2 - w / 2
            elif self.bottom_checkbox.isChecked():
                y_shift = ymin_orig - h - gap
                x_shift = (xmin_orig + xmax_orig) / 2 - w / 2
            elif self.left_checkbox.isChecked():
                y_shift = (ymin_orig + ymax_orig) / 2 - h / 2
                x_shift = xmin_orig - w - gap_2
            elif self.right_checkbox.isChecked():
                y_shift = (ymin_orig + ymax_orig) / 2 - h / 2
                x_shift = xmax_orig + gap_2
            else:  # Par défaut, en bas
                y_shift = ymin_orig - h - gap
                x_shift = (xmin_orig + xmax_orig) / 2 - w / 2

            # Ajustement des rectangles
            adjusted_rects = []
            for rect in rects:
                x0, y0, x1, y1 = rect
                adjusted_rect = (x0 + x_shift, y0 + y_shift, x1 + x_shift, y1 + y_shift)
                adjusted_rects.append(adjusted_rect)

            # Création des champs attributaires (simplifiés pour un seul niveau)
            fields = QgsFields()
            fields.append(QgsField(field1_name, QVariant.String))
            fields.append(QgsField("area_m2", QVariant.Double))
            fields.append(QgsField("area_km2", QVariant.Double))
            fields.append(QgsField("surf_ha", QVariant.Double))
            fields.append(QgsField("nb_poly", QVariant.Int))
            fields.append(QgsField("s_min_m2", QVariant.Double))
            fields.append(QgsField("s_max_m2", QVariant.Double))
            fields.append(QgsField("s_moy_m2", QVariant.Double))
            fields.append(QgsField("std_m2", QVariant.Double))
            fields.append(QgsField("s_med_m2", QVariant.Double))
            fields.append(QgsField("pourc_total", QVariant.Double))

            crs = self.layer.crs()
            # Nom de la couche : Treemap_<attribut niveau 1>_<nom couche initiale>
            treemap_name = f"Treemap_{field1_name}_{layer_name}"
            self.treemap_layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", treemap_name, "memory")
            pr = self.treemap_layer.dataProvider()
            pr.addAttributes(fields)
            self.treemap_layer.updateFields()

            # Génération des polygones
            for i, rect in enumerate(adjusted_rects):
                feat = QgsFeature()
                x0, y0, x1, y1 = rect
                polygon = [[QgsPointXY(x0, y0), QgsPointXY(x1, y0), QgsPointXY(x1, y1), QgsPointXY(x0, y1)]]
                geom = QgsGeometry.fromPolygonXY(polygon)
                feat.setGeometry(geom)

                cat = cats[i]
                area_m2 = round(sizes_list[i], 2)
                area_km2 = round(area_m2 / 1e6, 2)
                surf_ha = round(area_m2 / 1e4, 2)
                nb_poly = self.count_dict[cat]
                surfaces = self.surface_dict_m2[cat]
                s_min_m2 = round(min(surfaces), 2) if surfaces else 0
                s_max_m2 = round(max(surfaces), 2) if surfaces else 0
                s_moy_m2 = round(statistics.mean(surfaces), 2) if surfaces else 0
                std_m2 = round(statistics.stdev(surfaces), 2) if len(surfaces) > 1 else 0
                s_med_m2 = round(statistics.median(surfaces), 2) if surfaces else 0

                # Calcul du pourcentage
                pourc_total = (area_m2 / total) * 100 if total > 0 else 0

                feat.setAttributes([
                    cat, area_m2, area_km2, surf_ha, nb_poly,
                    s_min_m2, s_max_m2, s_moy_m2, std_m2, s_med_m2,
                    round(pourc_total, 2)
                ])
                pr.addFeature(feat)

            self.treemap_layer.updateExtents()
            QgsProject.instance().addMapLayer(self.treemap_layer)
            QMessageBox.information(self, "Success", "Treemap generated and added to the map.")
            self.treemap_layer = None
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error has occurred: {str(e)}")

    def closeEvent(self, event):
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        if self.treemap_layer:
            self.treemap_layer = None
        super().closeEvent(event)

class MainPluginTreemap:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):
        self.action = QAction("Treemap", self.iface.mainWindow())
        plugin_dir = os.path.dirname(__file__)
        icon_path = os.path.join(plugin_dir, "Treemap_icon1.png")
        self.action.setIcon(QIcon(icon_path))
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Treemap", self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        dialog = TreemapDialog(parent=self.iface.mainWindow(), iface=self.iface)

        dialog.exec_()

