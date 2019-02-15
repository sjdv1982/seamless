import atexit
from weakref import WeakSet
from contextlib import contextmanager

toplevel_register = set()

def _destroy_toplevels():
    for ctx in list(toplevel_register):
        ctx.destroy(from_del=True)

atexit.register(_destroy_toplevels)

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
        if macro is None:
            def bind_all(cctx):
                for childname, child in list(cctx._children.items()):
                    if not isinstance(child, UnboundContext):
                        continue
                    bound_ctx = Context()
                    bound_ctx._set_context(cctx, childname)
                    cctx._children[childname] = bound_ctx
                    child._bind(bound_ctx)                                        
                    bind_all(child)
            for ctx in list(toplevel_register):
                if isinstance(ctx, UnboundContext):
                    top = Context(toplevel=True)                    
                    ctx._bind(top)
                    toplevel_register.add(top)
                else:
                    bind_all(ctx)

    finally:
        _macro_mode = old_macro_mode
        _curr_macro = old_curr_macro
        if macro is None:
            for ctx in list(toplevel_register):
                if isinstance(ctx, UnboundContext):
                    toplevel_register.remove(ctx)
                else:
                    mount.scan(ctx)
        elif not _macro_mode:
            mount.scan(macro.ctx)

from .context import Context
from .unbound_context import UnboundContext            