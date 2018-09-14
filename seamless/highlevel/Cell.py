import weakref
from types import LambdaType
from .Base import Base
from ..midlevel import TRANSLATION_PREFIX
from ..core.lambdacode import lambdacode

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
        if attr == "schema":
            hcell = self._get_hcell()
            if hcell["celltype"] == "structured":
                cell = self._get_cell()
                return cell.handle.schema
        parent = self._parent()
        readonly = not test_lib_lowlevel(parent, self._get_cell())
        return SubCell(self._parent(), self, (attr,), readonly=readonly)

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        from .assign import assign_to_subcell
        parent = self._parent()
        assert not test_lib_lowlevel(parent, self._get_cell())
        assign_to_subcell(self, (attr,), value)
        ctx = parent._ctx
        if parent._as_lib is not None and not ctx._needs_translation:
            hcell = self._get_hcell()
            if hcell["path"] in parent._as_lib.partial_authority:
                parent._as_lib.needs_update = True
        parent.translate()

    @property
    def value(self):
        cell = self._get_cell()
        return cell.value

    @property
    def handle(self):
        cell = self._get_cell()
        return cell.handle

    @property
    def data(self):
        cell = self._get_cell()
        return cell.data

    def _set(self, value):
        #TODO: check if sovereign cell => disable warning!!
        from . import set_hcell
        try:
            cell = self._get_cell()
            cell.set(value)
            value = cell.value
        except AttributeError: #not yet been translated
            if callable(value):
                code = inspect.getsource(value)
                if isinstance(value, LambdaType) and func.__name__ == "<lambda>":
                    code = lambdacode(value)
                    if code is None:
                        raise ValueError("Cannot extract source code from this lambda")
                value = code
        hcell = self._get_hcell()
        set_hcell(hcell, value)

    def set(self, value):
        self._set(value)

    def _destroy(self):
        p = self._path
        nodes, connections = parent._graph
        for nodename in list(nodes.keys()):
            if nodename.startswith(p):
                nodes.pop(nodename)
        for con in list(connections):
            if con["source"].startswith(p) or con["target"].startswith(p):
                connections.remove(con)

    def __add__(self, other):
        self.set(self.value + other)

class SubCell(Cell):
    def __init__(self, parent, cell, subpath, readonly):
        fullpath = cell._path + subpath
        super().__init__(parent, fullpath)
        self._cell = weakref.ref(cell)
        self._readonly = readonly
        self._subpath = subpath

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        from .assign import assign_to_subcell
        parent = self._parent()
        assert not test_lib_lowlevel(parent, self._get_cell())
        path = self._subpath + attr
        assign_to_subcell(self, path, value)
        ctx = parent._ctx
        if parent._as_lib is not None and not ctx._needs_translation:
            hcell = self._get_hcell()
            if hcell["path"] in parent._as_lib.partial_authority:
                parent._as_lib.needs_update = True
        parent.translate()

    def __getattr__(self, attr):
        parent = self._parent()
        readonly = self._readonly
        return SubCell(self._parent(), self, self._subpath + (attr,), readonly=readonly)

    def set(self, value):
        assert not self._readonly
        print("UNTESTED SubCell.set")
        cell = self._cell
        attr = self._subpath[-1]
        if len(self._subpath) == 1:
            return setattr(cell, attr, value)
        else:
            parent_subcell = SubCell(self._parent(), cell, self._subpath[:-1], False)
            return setattr(parent_subcell, attr, value)

    @property
    def _virtual_path(self):
        cell = self._cell()
        p = cell._virtual_path
        if p is None:
            return None
        return p + self._subpath

from .Library import test_lib_lowlevel
