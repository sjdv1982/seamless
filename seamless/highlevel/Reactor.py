import weakref
import functools
from .Cell import Cell
from .proxy import Proxy
from .pin import InputPin, OutputPin
from .Base import Base
from .Library import test_lib_lowlevel
from ..midlevel import TRANSLATION_PREFIX

from ..core.context import Context as CoreContext

class Reactor(Base):
    def __init__(self, parent, path):
        super().__init__(parent, path)
        parent._children[path] = self


    def __setattr__(self, attr, value):
        from .assign import assign_connection
        from ..midlevel.copying import fill_structured_cell_value
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        translate = False
        parent = self._parent()
        rc = self._get_rc()
        hrc = self._get_hrc()
        if attr in ("code_start", "code_update", "code_stop"):
            cell = getattr(rc, attr)
            assert not test_lib_lowlevel(parent, cell)
            cell.set(value)
            hrc[attr] = cell.value
        else:
            io = getattr(rc, hrc["IO"])
            assert not test_lib_lowlevel(parent, io)
            if attr not in hrc["pins"]:
                hrc["pins"][attr] = {"submode": "silk", "io": "input"}
                translate = True
            if isinstance(value, Cell):
                target_path = self._path + (attr,)
                assert value._parent() == parent
                #TODO: check existing inchannel connections (cannot be the same or higher)
                assign_connection(parent, value._path, target_path, False)
                translate = True
            else:
                rc = self._get_rc()
                io = getattr(rc, hrc["IO"])
                setattr(io.handle, attr, value)
                fill_structured_cell_value(io, hrc, "stored_state_input", "cached_state_input")
            hrc.pop("in_equilibrium", None)
            if parent._as_lib is not None and not translate:
                if hrc["path"] in parent._as_lib.partial_authority:
                    parent._as_lib.needs_update = True
            if translate:
                parent._translate()


    def _get_rc(self):
        parent = self._parent()
        parent.translate()
        p = getattr(parent._ctx, TRANSLATION_PREFIX)
        for subpath in self._path:
            p = getattr(p, subpath)
        assert isinstance(p, CoreContext)
        return p

    def _get_hrc(self):
        parent = self._parent()
        return parent._graph[0][self._path]
