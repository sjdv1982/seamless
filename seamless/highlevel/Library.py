"""
Two mechanisms of library update:
- Direct library update.
  This uses low-level library registration.
  Whenever an authoritative, non-slave changes value, any libcell is directly updated.
- Indirect library update (high level)
  The high-level keeps track of all high-level macros that copy a library from stdlib.
  Whenever the library is re-translated or its constructor/copier changes, then
   the high-level macro is re-executed
"""
class _Library:
    def __setattr__(self, attr, value):
        from .Context import Context
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        assert isinstance(value, Context)
        value._from_lib = None
        value._as_lib = attr
        object.__setattr__(self, attr, value)
        value.translate(force=True)

stdlib = _Library()

def get_lib_paths(ctx):
    from .Context import Context
    assert isinstance(ctx, Context)
    lib_paths = {}
    for subcontext, sub in ctx._graph.subcontexts.items():
        from_lib = sub.get("from_lib")
        if from_lib is not None:
            lib_paths[subcontext] = from_lib
    return lib_paths

def check_lib_core(ctx, obj):
    """Check that a core object does not point to an authoritative cell imported from a library"""
    from ..core import SeamlessBase
    from ..core.library import lib_has_path
    assert isinstance(obj, SeamlessBase)
    lib_paths = get_lib_paths(ctx)
    objpath = obj.path
    for lib_path in lib_paths:
        if objpath[:len(lib_path)] != lib_path:
            continue
        libname = lib_paths[lib_path]
        tail = objpath[len(lib_path):]
        p = ".".join(tail)
        assert not lib_has_path(libname, p)
