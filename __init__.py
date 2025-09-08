# coding=utf-8
# (c) JC BAUDIN 2025 09 07

def classFactory(iface):
    from .treemap import MainPluginTreemap
    return MainPluginTreemap(iface)

