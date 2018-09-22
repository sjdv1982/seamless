from copy import deepcopy

def copy_context(nodes, connections, path):
    new_nodes = {}
    new_connections = []
    for p in nodes:
        if p[:len(path)] != path:
            continue
        pp = p[len(path):]
        node = deepcopy(nodes[p])
        node["path"] = pp
        new_nodes[pp] = node
    for con in connections:
        source, target = con["source"], con["target"]
        if source[:len(path)] != path:
            continue
        if target[:len(path)] != path:
            continue
        new_con = deepcopy(con)
        new_con["source"] = source[len(path):]
        new_con["target"] = target[len(path):]
        new_connections.append(new_con)

def fill_structured_cell_value(cell, node, label_auth, label_cached):
    from ..core.structured_cell import StructuredCellState
    """
    Fills the state of a structured cell into the node, in two forms:
    - A. Containing only the authoritative state
    - B. Containing the full state
    For normal cells, these are redundant:
      A == B for authoritative cells, A is None otherwise.
    For structured cells, it is much less clear cut, as they may have
     partial authority (having some but not all values dependent on inchannels)
    In that case, both the authoritative part of the state (under label_auth)
     and the full state (under)
    """
    if cell.has_authority: #cell has at least some authority
        state = StructuredCellState().set(cell, only_auth=True)
        node[label_auth] = state
    else:
        node.pop(label_auth, None)
    if not cell.authoritative: #cell has at least some non-authority
        state = StructuredCellState().set(cell, only_auth=False)
        node[label_cached] = state
    else:
        node.pop(label_cached, None)

def fill_cell_value(cell, node):
    from ..core.structured_cell import StructuredCell
    if isinstance(cell, StructuredCell):
        fill_structured_cell_value(cell, node, "stored_state", "cached_state")
    else:
        if cell.authoritative:
            node["stored_value"] = child.value
            node.pop("cached_value", None)
        else:
            node["cached_value"] = child.value
            node.pop("stored_value", None)

def fill_cell_values(ctx, nodes, path=None):
    from ..highlevel.Cell import Cell
    from ..highlevel.Transformer import Transformer
    from ..core.structured_cell import StructuredCell
    manager = ctx._ctx._get_manager()
    try:
        manager.deactivate()
        for p in nodes:
            pp = path + p if path is not None else p
            child = ctx._children.get(pp)
            node = nodes[p]
            if isinstance(child, Transformer):
                transformer = child._get_tf()
                if transformer.status() == "OK":
                    node["in_equilibrium"] = True
                input_name = node["INPUT"]
                inp = getattr(transformer, input_name)
                assert isinstance(inp, StructuredCell)
                fill_structured_cell_value(inp, node, "stored_state_input", "cached_state_input")
                if node["with_schema"]:
                    result_name = node["RESULT"]
                    result = getattr(transformer, result_name)
                    assert isinstance(result, StructuredCell)
                    fill_structured_cell_value(result, node, None, "cached_state_result")
                continue
            elif isinstance(child, Cell):
                assert node["type"] == "cell", (pp, node["type"])
                cell = child._get_cell()
                fill_cell_value(cell, node)
            else:
                raise TypeError(child)
    finally:
        manager.activate(only_macros=False)

"""
def clear_cached_cell_values(ctx, nodes):
    from ..highlevel.Cell import Cell
    from ..highlevel.Transformer import Transformer
    from ..core.structured_cell import StructuredCell
    for p in nodes:
        node = nodes[p]
        if node["type"] == "transformer":
            node.pop("stored_state_input", None)
            node.pop("cached_state_input", None)
            node.pop("cached_state_result", None)
            node.pop("in_equilibrium", None)
        elif node["type"] == "cell":
            if node["celltype"] == "structured":
                node.pop("stored_state", None)
                node.pop("cached_state", None)
            else:
                node.pop("cached_value", None)
"""
