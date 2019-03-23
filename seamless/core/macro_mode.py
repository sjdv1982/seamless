import atexit
from weakref import WeakSet
from contextlib import contextmanager

_toplevel_register = set()
_toplevel_registered = set()

def register_toplevel(ctx):
    if _macro_mode_off:
        return
    _toplevel_register.add(ctx)

def unregister_toplevel(ctx):    
    _toplevel_register.discard(ctx)
    _toplevel_registered.discard(ctx)

def _destroy_toplevels():
    for ctx in list(_toplevel_registered):
        ctx.destroy(from_del=True)

atexit.register(_destroy_toplevels)

_macro_mode = False
_curr_macro = None
_macro_mode_off = False

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
    if macro is None:
        assert not _macro_mode 
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
            for ctx in list(_toplevel_register):
                if isinstance(ctx, UnboundContext):
                    top = ctx._root_
                    assert top is not None
                    ctx._bind(top)
                    _toplevel_registered.add(top)
                else:
                    _toplevel_registered.add(ctx)
                    bind_all(ctx)        
        ok = True
    finally:
        _macro_mode = old_macro_mode
        _curr_macro = old_curr_macro
        if not ok and old_context is not None:
            old_context._get_manager().activate_context(old_context)
        if macro is None:
            for ub_ctx in list(_toplevel_register):
                if isinstance(ub_ctx, UnboundContext):
                    _toplevel_register.remove(ub_ctx)
                    ctx = ub_ctx._bound
                    if ctx is None or not ok:
                        continue
                    assert isinstance(ctx, Context)
                    mount.scan(ctx, old_context=None)
        elif not _macro_mode:
            _toplevel_register.clear()
            if ok:
                mount.scan(macro._gen_context, old_context=old_context)

@contextmanager
def macro_mode_off():
    global _macro_mode, _curr_macro, _macro_mode_off
    old_macro_mode = _macro_mode
    old_macro_mode_off = _macro_mode_off
    old_macro = _curr_macro
    _macro_mode = False
    _macro_mode_off = True
    _curr_macro = None
    try:
        yield
    finally:
        _macro_mode = old_macro_mode
        _curr_macro = old_macro
        _macro_mode_off = old_macro_mode_off

from .context import Context
from .unbound_context import UnboundContext            