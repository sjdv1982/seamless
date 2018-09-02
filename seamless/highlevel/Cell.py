import weakref
from .Base import Base

class Cell(Base):
    _virtual_path = None
    def __init__(self, parent, path):
        super().__init__(parent, path)
        parent._children[path] = self

    def __str__(self):
        return str(self._get_cell())

    def _get_cell(self):
        parent = self._parent()
        parent.translate()
        p = parent._ctx.translated
        for subpath in self._path:
            p = getattr(p, subpath)
        return p

    def _get_hcell(self):
        parent = self._parent()
        return parent._graph[0][self._path]

    def self(self):
        raise NotImplementedError

    def __getattr__(self, attr):
        #TODO: add subcell to parent._children as well!
        #TODO: check if already in parent._children!
        return SubCell(self._parent(), self, self._path + (attr,))

    @property
    def value(self):
        cell = self._get_cell()
        return cell.value

    def set(self, value):
        #TODO: check if sovereign cell!!
        #TODO: disable warning!!
        cell = self._get_cell()
        cell.set(value)
        hcell = self._get_hcell()
        hcell["value"] = cell.value

    def _destroy(self):
        p = self._path
        nodes, connections = parent._graph
        for nodename in list(nodes.keys()):
            if nodename.startswith(p):
                nodes.pop(nodename)
        for con in list(connections):
            if con["source"].startswith(p) or con["target"].startswith(p):
                connections.remove(con)

class SubCell(Cell):
    def __init__(self, parent, cell, path):
        super().__init__(parent, path)
        self._cell = weakref.ref(cell)

    def _get_hcell(self):
        raise NotImplementedError
