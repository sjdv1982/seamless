import weakref
from enum import Enum

class IpyString(str):
    def _repr_pretty_(self, p, cycle):
        return p.text(str(self))

from .macro_mode import with_macro_mode

class SeamlessBase:
    _destroyed = False
    _context = None
    _fallback_path = None
    name = None

    StatusFlags = Enum('StatusFlags', ('OK', 'PENDING', 'UNDEFINED', 'UNCONNECTED', 'ERROR'))
    _status = StatusFlags.UNDEFINED

    def _is_sealed(self):
        assert self._context is not None #worker/cell must have a context
        return self._context()._is_sealed()

    @property
    def path(self):
        if self._context is None:
            return ()
        elif self._fallback_path is not None:
            return self._fallback_path
        elif self._context().path is None:
            return ("<None>", self.name)
        else:
            return self._context().path + (self.name,)

    def _validate_path(self, required_path=None):
        if required_path is None:
            required_path = self.path
        else:
            assert self.path == required_path, (self.path, required_path)
        return required_path

    def _set_context(self, context, name):
        from .context import Context
        assert isinstance(context, Context)
        assert self._context is None
        ctx = weakref.ref(context)
        self._context = ctx
        self.name = name
        self._fallback_path =  self.path
        return self

    def _get_manager(self):
        assert self._context is not None #worker/cell must have a context
        return self._context()._get_manager()

    def _root(self):
        assert self._context is not None #worker/cell must have a context
        return self._context()._root()

    def _format_path(self):
        if self.path is None:
            ret = "<None>"
        else:
            ret = "." + ".".join(self.path)
        return ret

    def __str__(self):
        ret = "Seamless object: " + self._format_path()
        return ret

    def __repr__(self):
        return self.__str__()

    def _set_macro_object(self, macro_object):
        self._macro_object = macro_object

    @property
    def self(self):
        return self

    def destroy(self):
        self._destroyed = True

class SeamlessBaseList(list):
    def __str__(self):
        return str([v._format_path() for v in self])

link_counter = 0
class Link(SeamlessBase):
    _mount = None
    def __init__(self, obj):
        from . import macro_register
        global link_counter
        assert isinstance(obj, SeamlessBase)
        self._linked = obj
        link_counter += 1
        self._counter = link_counter
        macro_register.add(self)

    def __hash__(self):
        return -self._counter

    @property
    def _seal(self):
        return self._linked._seal

    @_seal.setter
    def _seal(self, value):
        pass

    def get_linked(self):
        linked = self._linked
        if isinstance(linked, Link):
            linked = linked.get_linked()
        return linked

    def connect(self, target):
        manager = self._get_manager()
        manager.connect_link(self, target)
        return self

    def __getattr__(self, attr):
        from .layer import Path
        linked = self.get_linked()
        result = getattr(linked, attr)
        if isinstance(result, Path):
            return getattr(Path(self), attr)
        else:
            return result

    def __str__(self):
        ret = "Seamless link: %s to %s" % (self._format_path(), self._linked)
        return ret

def link(obj):
    return Link(obj)

from .macro_mode import get_macro_mode, macro_register, macro_mode_on
from . import cell as cell_module
from .cell import Cell, CellLikeBase, cell
from .cell import textcell, pythoncell, pytransformercell, pymacrocell, \
 pyreactorcell, ipythoncell, jsoncell, csoncell, arraycell, mixedcell, signal
from .library import libcell, libmixedcell
from . import context as context_module
from .context import Context, context
from .worker import Worker
from .transformer import Transformer, transformer
from .mount import mountmanager
from .structured_cell import StructuredCell
from .layer import path
from .macro import macro
from .reactor import reactor
from . import cache
