from ..core.library import build, register
from . import copying
from .translate import find_channels

def register_library(ctx, hctx, libname):
    from ..core import library
    from ..core.unbound_context import UnboundContext
    if isinstance(ctx, UnboundContext):
        ctx = ctx._bound
    nodes, connections, _ = hctx._graph
    assert not hctx._translating
    try:
        hctx._translating = True
        copying.fill_checksums(ctx._get_manager(), nodes)
        lib = build(ctx)
        library.register(libname, lib)
    finally:
        hctx._translating = False

def get_lib_path(nodepath, from_lib_paths):
    raise NotImplementedError ### livegraph branch
    """Gets the path of nodepath within the library that the node comes from (if any)"""
    for p in range(len(nodepath), 0, -1):
        if nodepath[:p] in from_lib_paths:
            head = from_lib_paths[nodepath[:p]]
            break
    else:
        return None
    tail = nodepath[p:]
    if len(tail):
        tail = "." + ".".join(tail)
    else:
        tail = ""
    return head + tail
