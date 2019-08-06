import atexit
from weakref import WeakSet
from contextlib import contextmanager

_toplevel_register = set()
_toplevel_registered = set()
_toplevel_managers = set()

def register_toplevel(ctx):
    if _macro_mode_off:
        return
    manager = ctx._get_manager()
    assert manager is not None
    # Add toplevel manager even if unbound; else it will be destroyed!!
    _toplevel_managers.add(manager)
    _toplevel_register.add(ctx)

def unregister_toplevel(ctx):
    manager = ctx._get_manager()
    if manager is not None:
        _toplevel_managers.discard(manager)
    _toplevel_register.discard(ctx)
    _toplevel_registered.discard(ctx)

def _destroy_toplevels():
    for manager in list(_toplevel_managers):
        manager.destroy(from_del=True)
    for ctx in list(_toplevel_registered):
        manager = ctx._get_manager()
        if manager is not None:
            manager.destroy(from_del=True)
    transformation_cache.destroy()

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
    from .context import Context
    from .unbound_context import UnboundContext                
    global _macro_mode, _curr_macro
    if macro is None:
        assert not _macro_mode 
    old_macro_mode = _macro_mode
    old_curr_macro = _curr_macro
    _macro_mode = True
    _curr_macro = macro
    old_context = macro._gen_context if macro is not None else None
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
                    old_manager = ctx._get_manager()
                    ctx._bind(top)
                    assert ctx._bound
                    new_manager = top._get_manager()                    
                    _toplevel_registered.add(top)
                    # we kept the unbound manager alive, now we can get rid of it...
                    _toplevel_managers.discard(old_manager)
                    _toplevel_registered.add(top)
                    _toplevel_managers.add(new_manager)
                else:
                    _toplevel_registered.add(ctx)
                    _toplevel_managers.add(ctx._get_manager())
                    bind_all(ctx)        
        ok = True
    finally:
        _macro_mode = old_macro_mode
        _curr_macro = old_curr_macro
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


from .cache.transformation_cache import transformation_cache