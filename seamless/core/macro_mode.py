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
    old_context = macro._gen_context if macro is not None else None
    if old_context is not None:
        old_context._get_manager().deactivate_context(old_context)
    try:
        ok = False
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
        ok = True
    finally:
        _macro_mode = old_macro_mode
        _curr_macro = old_curr_macro
        if not ok and old_context is not None:
            old_context._get_manager().activate_context(old_context)
        if macro is None:
            for ub_ctx in list(toplevel_register):
                if isinstance(ub_ctx, UnboundContext):
                    toplevel_register.remove(ub_ctx)
                    ctx = ub_ctx._bound
                    if ctx is None or not ok:
                        continue
                    mount.scan(ctx, old_context=None)
        elif not _macro_mode:
            if ok:
                mount.scan(macro._gen_context, old_context=old_context)

from .context import Context
from .unbound_context import UnboundContext            