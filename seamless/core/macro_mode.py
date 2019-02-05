import atexit
from weakref import WeakSet
from contextlib import contextmanager

toplevel_register = set()

def _destroy_toplevels():
    for ctx in list(toplevel_register):
        ctx.destroy(from_del=True)

atexit.register(_destroy_toplevels)


class MacroRegister:
    def __init__(self):
        self.stack = WeakSet()
    def add(self, item):
        self.stack.add(item)

macro_register = MacroRegister()

_macro_mode = False
_curr_macro = None

def get_macro_mode():
    return _macro_mode

def curr_macro():
    if not _macro_mode:
        return None
    return _curr_macro

@contextmanager
def macro_mode_on(macro=None):
    from . import mount
    global _macro_mode, _curr_macro
    old_macro_mode = _macro_mode
    old_curr_macro = _curr_macro
    _macro_mode = True
    _curr_macro = macro
    try:
        yield
        if not old_macro_mode:
            mount.resolve_register(macro_register.stack)
    finally:
        _macro_mode = old_macro_mode
        _curr_macro = old_curr_macro
        if not old_macro_mode:
            macro_register.stack.clear()
            for ctx in toplevel_register:
                ctx._get_manager().leave_macro_mode()

def with_macro_mode(func):
    def with_macro_mode_wrapper(self, *args, **kwargs):
        if not get_macro_mode():
            if self._context is None: #worker construction
                return func(self, *args, **kwargs)
            ctx = self._root()
            if not ctx._direct_mode:
                raise Exception("This operation requires macro mode, since the toplevel context was constructed in macro mode")
            else:
                with macro_mode_on():
                    result = func(self, *args, **kwargs)
                return result
        else:
            return func(self, *args, **kwargs)
    return with_macro_mode_wrapper
