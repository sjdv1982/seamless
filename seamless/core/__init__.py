import weakref
from enum import Enum

class IpyString(str):
    def _repr_pretty_(self, p, cycle):
        return p.text(str(self))

class SeamlessBase:
    _destroyed = False
    _macro_object = None # macro object that CREATED this instance
    _context = None
    _last_context = None
    name = None

    StatusFlags = Enum('StatusFlags', ('OK', 'PENDING', 'UNDEFINED', 'UNCONNECTED', 'ERROR'))
    _status = StatusFlags.UNDEFINED

    @property
    def path(self):
        if self._context is None:
            return ()
        elif self._context.path is None:
            return ("<None>", self.name)
        else:
            return self._context.path + (self.name,)

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
        self._last_context = context
        self._context = context
        self.name = name
        return self

    def _get_manager(self):
        assert self._context is not None #worker/cell must have a context
        return self._context._get_manager()

    def _macro_control(self):
        if self._macro_object is not None:
            return self

        ret = None
        if self.context is not None:
            ret = self.context._macro_control()
        else:
            return None

    def format_path(self):
        if self.path is None:
            ret = "<None>"
        else:
            ret = "." + ".".join(self.path)
        return ret

    def __str__(self):
        ret = "Seamless object: " + self.format_path()
        return ret

    def __repr__(self):
        return self.__str__()

    @property
    def macro(self):
        """Returns the macro object associated with this construct"""
        return self._macro_object

    def _set_macro_object(self, macro_object):
        self._macro_object = macro_object

class SeamlessBaseList(list):
    def __str__(self):
        return str([v.format_path() for v in self])

from . import cell as cell_module
from .cell import Cell, cell, textcell, pytransformercell
from . import context as context_module
from .context import Context, context
from .worker import Worker
from .transformer import Transformer, transformer
from .mount import mountmanager
from .structured_cell import StructuredCell
