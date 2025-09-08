# coding=utf-8
"""
/***************************************************************************
 Treemap
                                 A QGIS plugin
 This plugin allows you to create a treemap visualization from polygon layers as a layer itself in order to directly choose to make it appear in the print composer.
 
                              -------------------
        begin                : 2025-09-08
        git sha              : $Format:%H$
        copyright            : (C) 2025 by jc Baudin
        email                : jeanchristophebaudin@ymail.com
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
__author__ = 'Jean-Christophe Baudin'
__date__ = '2025-09-07'
__copyright__ = '(C) 2025 by Jean-Christophe Baudin'

def classFactory(iface):
    from .treemap import MainPluginTreemap
    return MainPluginTreemap(iface)
