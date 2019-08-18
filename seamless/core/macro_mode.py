import atexit
from weakref import WeakSet
from contextlib import contextmanager

_toplevel_registrable = set()
_toplevel_registered = set()
_toplevel_managers = set()

def register_toplevel(ctx):
    manager = ctx._get_manager()
    assert manager is not None
    if not _macro_mode:
        _toplevel_managers.add(manager)
        _toplevel_registered.add(ctx)
    else:
        # Add toplevel manager even if unbound; else it will be destroyed!!
        _toplevel_managers.add(manager)
        _toplevel_registrable.add(ctx)

def unregister_toplevel(ctx):
    manager = ctx._get_manager()
    if manager is not None:
        _toplevel_managers.discard(manager)
    _toplevel_registrable.discard(ctx)
    _toplevel_registered.discard(ctx)

def _destroy_toplevels():
    for manager in list(_toplevel_managers):
        manager.destroy(from_del=True)
    for ctx in list(_toplevel_registered):
        unregister_all(ctx)
        manager = ctx._get_manager()
        if manager is not None:
            manager.destroy(from_del=True)
    transformation_cache.destroy()

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
    from .context import Context
    from .cell import Cell
    from .unbound_context import UnboundContext                
    from .macro import _global_paths
    global _macro_mode, _curr_macro
    if _macro_mode:
        raise Exception("macro mode cannot be re-entrant")
        assert not _macro_mode 
    _macro_mode = True
    _curr_macro = macro
    old_context = macro._gen_context if macro is not None else None    
    try:
        _mount_scans = []
        if old_context is not None:
            old_context.destroy()
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
            for ctx in list(_toplevel_registrable):
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
            for ub_ctx in list(_toplevel_registrable):
                if isinstance(ub_ctx, UnboundContext):
                    _toplevel_registrable.remove(ub_ctx)
                    ctx = ub_ctx._bound
                    if ctx is None:
                        continue
                    assert isinstance(ctx, Context)
                    _mount_scans.append((ctx, None))
            for ctx in _toplevel_registered:
                for pathname, path in _global_paths.get(ctx, {}).items():
                    cctx = ctx
                    for subpathname in pathname:                    
                        try:
                            cctx = getattr(cctx, subpathname)
                        except (AttributeError, KeyError, TypeError, AssertionError):
                            break
                    else:
                        if isinstance(cctx, Cell):
                            path._bind(cctx, True)
        if macro is not None:            
            # TODO: recycle mount items
            # Now, Old context has been destroyed already
            ###_mount_scans.append((macro._gen_context, old_context))
            _mount_scans.append((macro._gen_context, None))

        mount_changed = False
        for scan_ctx, old_scan_ctx in _mount_scans:
            curr_mount_changed = mount.scan(
                scan_ctx, old_context=old_scan_ctx
            )
            if curr_mount_changed is not None and curr_mount_changed != ({}, set(), {}):
                mount_changed = True

        if mount_changed:
            mount.mountmanager.tick()

    finally:
        _toplevel_registrable.clear()
        _macro_mode = False

from .cache.transformation_cache import transformation_cache
from .library import unregister_all
