"""
Слой совместимости для плагинов, написанных под FunPayCardinal.

Старое имя модуля сохранено как псевдоним `Utils/vertex_tools.py`.
Новый код должен импортировать `Utils.vertex_tools` напрямую.
"""
from Utils import vertex_tools as _vertex_tools

# Пробрасываем всё публичное содержимое vertex_tools под старым именем модуля.
# Делается через globals(), а не через "import *", чтобы одинаково перенести и
# функции, и константы, и скомпилированные регулярные выражения.
globals().update({
    _name: _value
    for _name, _value in vars(_vertex_tools).items()
    if not _name.startswith("__")
})

del _vertex_tools
