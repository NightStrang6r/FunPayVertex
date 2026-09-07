"""
Слой совместимости для плагинов, написанных под FunPayCardinal.
"""
from vertex import Vertex, PluginData, get_vertex  # noqa: F401

Cardinal = Vertex
get_cardinal = get_vertex