"""
Слой совместимости для плагинов, написанных под FunPayCardinal.

При ребрендинге `cardinal.py` был переименован в `vertex.py`, а класс
`Cardinal` - в `Vertex`. Сторонние плагины ссылаются на старые имена:

    if TYPE_CHECKING:
        from cardinal import Cardinal

    def handler(c: Cardinal, e: NewMessageEvent): ...

Чаще всего такой импорт стоит под `TYPE_CHECKING` и в рантайме не выполняется,
но полагаться на это нельзя: плагин может импортировать модуль и обычным
образом. `Cardinal` здесь - тот же самый объект класса, что и `Vertex`,
поэтому isinstance-проверки и аннотации ведут себя одинаково.

Новый код должен импортировать `vertex` напрямую.
"""
from vertex import Vertex, PluginData, get_vertex  # noqa: F401

#: Старое имя класса ядра.
Cardinal = Vertex

#: Старое имя функции доступа к запущенному экземпляру.
get_cardinal = get_vertex
