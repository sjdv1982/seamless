from ..core.library import build, register
from . import copy_context, TRANSLATION_PREFIX

def register_library(ctx_functor, hctx, libname):
    from ..core import library
    ctx = ctx_functor()
    nodes, _, _ = hctx._graph
    copy_context.fill_cell_values(hctx, nodes)
    copy_context.warn_partial_authority(hctx, nodes)
    lib = build(ctx)
    library.register(libname, lib)

def get_lib_path(nodepath, from_lib_paths):
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
