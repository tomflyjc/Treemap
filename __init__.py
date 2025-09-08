# coding=utf-8

def classFactory(iface):
    from .treemap import MainPluginTreemap
    return MainPluginTreemap(iface)
