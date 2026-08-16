"""
Слой совместимости для плагинов, написанных под FunPayCardinal.

При ребрендинге модуль `Utils/cardinal_tools.py` был переименован в
`Utils/vertex_tools.py`. Сторонние плагины импортируют его по старому имени
прямо в рантайме, например:

    from Utils import cardinal_tools

Без этого модуля такой плагин падал бы с ImportError, и загрузчик молча
пропускал бы его (`Vertex.load_plugins` перехватывает ошибку и пишет одну
строку в лог). Поэтому старое имя сохранено как псевдоним.

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
