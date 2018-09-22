import weakref
import inspect
from types import LambdaType
from .Base import Base
from ..midlevel import TRANSLATION_PREFIX
from ..core.lambdacode import lambdacode
from ..silk import Silk

class Cell(Base):
    _virtual_path = None
    def __init__(self, parent, path):
        super().__init__(parent, path)
        parent._children[path] = self

    def __str__(self):
        try:
            return str(self._get_cell())
        except AttributeError:
            return("Cell %s in dummy mode" % ("." + ".".join(self._path)))

    def _get_cell(self):
        parent = self._parent()
        if parent._dummy:
            raise AttributeError
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

    def mount(self, mount):
        hcell = self._get_hcell()
        hcell["mount"] = mount
        parent.translate(force=True)

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        from .assign import assign_to_subcell
        parent = self._parent()
        assert not parent._dummy
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
        parent = self._parent()
        if parent._dummy:
            hcell = self._get_hcell()
            if hcell["celltype"] == "structured":
                state = hcell.get("stored_state", None)
                if state is None:
                    state = hcell.get("cached_state", None)
                value = None
                if state is not None:
                    if hcell["silk"]:
                        value = Silk(data=state.data, schema=state.schema)
                    else:
                        value = state.data
            else:
                value = hcell.get("stored_value", None)
                if value is None:
                    value = hcell.get("cached_value", None)
            return value
        else:
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
        from ..silk import Silk
        try:
            cell = self._get_cell()
            cell.set(value)
            value = cell.value
        except AttributeError: #not yet been translated
            if callable(value) and not isinstance(value, Silk):
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

    def __add__(self, other):
        self.set(self.value + other)

    @property
    def celltype(self):
        hcell = self._get_hcell()
        return hcell["celltype"]

    @celltype.setter
    def celltype(self, value):
        assert value in ("structured", "text", "code", "json"), value #TODO, see translate.py
        hcell = self._get_hcell()
        hcell["celltype"] = value
        self._update_dep()

    def _update_dep(self):
        self._parent()._depsgraph.update_path(self._path)

class SubCell(Cell):
    def __init__(self, parent, cell, subpath, readonly):
        assert not parent._dummy #cannot access cell.attr in constructors, use cell.value.attr instead
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
