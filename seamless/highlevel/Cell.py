import weakref
from .Base import Base
from ..midlevel import TRANSLATION_PREFIX

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
        p = getattr(parent._ctx, TRANSLATION_PREFIX)
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
        parent = self._parent()
        check_lib_core(parent, self._get_cell())
        return SubCell(self._parent(), self, self._path + (attr,))

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        parent = self._parent()
        check_lib_core(parent, self._get_cell())
        raise NotImplementedError
        #TODO
        '''
        if parent._as_lib is not None and not translate:
            if htf["path"] in parent._as_lib.partial_authority:
                parent._as_lib.needs_update = True
        '''
        #TODO: get a handle on the underlying Silk data for modification
        # This also triggers parent._as_lib.needs_update = True

    @property
    def value(self):
        cell = self._get_cell()
        return cell.value

    def _set(self, value):
        #TODO: check if sovereign cell => disable warning!!
        cell = self._get_cell()
        cell.set(value)
        hcell = self._get_hcell()
        hcell["value"] = cell.value
        ctx = self._parent()

    def set(self, value):
        self._set(value)
        ctx = self._parent()

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

from .Library import check_lib_core
