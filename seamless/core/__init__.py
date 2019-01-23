import weakref

class IpyString(str):
    def _repr_pretty_(self, p, cycle):
        return p.text(str(self))

from .macro_mode import with_macro_mode

class SeamlessBase:
    _destroyed = False
    _context = None
    name = None

    @property
    def path(self):
        if self._context is None:
            return ()
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

from .macro_mode import get_macro_mode, macro_register, macro_mode_on
from . import cell as cell_module
from .cell import Cell, cell
from .cell import textcell, pythoncell, pytransformercell, pymacrocell, \
 pyreactorcell, ipythoncell, plaincell, csoncell, arraycell, mixedcell
from .library import libcell, libmixedcell
from . import context as context_module
from .context import Context, context, path
from .worker import Worker
from .transformer import Transformer, transformer
from .mount import mountmanager
from .structured_cell import StructuredCell
from .macro import Macro, macro
from .reactor import Reactor, reactor
from .link import link
