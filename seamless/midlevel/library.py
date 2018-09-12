from ..core.library import build, register
from . import copy_context, TRANSLATION_PREFIX
from .translate import find_channels

def register_library(ctx, hctx, libname):
    from ..core import library
    nodes, connections, _ = hctx._graph
    copy_context.fill_cell_values(hctx, nodes)
    partial_authority = get_partial_authority(hctx, nodes, connections)
    lib = build(ctx)
    library.register(libname, lib)
    return partial_authority

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

"""
def _warn_partial_authority(cell):
    from ..core.structured_cell import StructuredCell
    assert isinstance(cell, StructuredCell)
    if cell.has_authority and not cell.authoritative:
        print("WARNING: StructuredCell %s has partial authority, direct library update will not work" % cell)

def warn_partial_authority(ctx, nodes):
    from ..highlevel.Cell import Cell
    from ..highlevel.Transformer import Transformer
    from ..core.structured_cell import StructuredCell
    for p in nodes:
        child = ctx._children.get(p)
        node = nodes[p]
        if isinstance(child, Transformer):
            transformer = child._get_tf()
            input_name = node["INPUT"]
            inp = getattr(transformer, input_name)
            _warn_partial_authority(inp)
            if node["with_schema"]:
                result_name = node["RESULT"]
                result = getattr(transformer, result_name)
                _warn_partial_authority(result)
            continue
        if not isinstance(child, Cell):
            continue
        assert node["type"] == "cell", (pp, node["type"])
        cell = child._get_cell()
        if isinstance(cell, StructuredCell):
            _warn_partial_authority(cell)
"""

def get_partial_authority(ctx, nodes, connections):
    from ..highlevel.Cell import Cell
    from ..highlevel.Transformer import Transformer
    from ..core.structured_cell import StructuredCell
    connection_paths = [(con["source"], con["target"]) for con in connections]
    partial_authority = set()
    for p in nodes:
        child = ctx._children.get(p)
        node = nodes[p]
        if isinstance(child, Transformer):
            transformer = child._get_tf()
            if not len(node["values"]):
                continue #no authority at all
            inchannels, _ = find_channels(p, connection_paths)
            inchannels = [i for i in inchannels if i != "code" and i[0] != "code"]
            if len(inchannels):
                partial_authority.add(p)
            continue
        if not isinstance(child, Cell):
            continue
        assert node["type"] == "cell", (pp, node["type"])
        cell = child._get_cell()
        if isinstance(cell, StructuredCell):
            inchannels, _ = find_channels(p, connection_paths)
            if not len(inchannels):
                continue #complete authority
            elif inchannels == [()]:
                continue #no authority
            partial_authority.add(p)
    return partial_authority
