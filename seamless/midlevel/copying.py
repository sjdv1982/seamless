from ..mixed import MixedBase
from copy import deepcopy
from ..core import Link as core_link

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
    state = None
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
    return state

def fill_simple_cell_value(cell, node, label_auth, label_cached):
    if isinstance(cell, core_link):
        node.pop(label_auth, None)
        node.pop(label_cached, None)
        return
    value = cell.value
    if isinstance(value, MixedBase):
        value = value.value
    if cell.authoritative:
        node[label_auth] = value
        node.pop(label_cached, None)
    else:
        node[label_cached] = value
        node.pop(label_auth, None)
    return value

def fill_cell_value(cell, node):
    from ..core import Cell
    from ..core.structured_cell import StructuredCell
    if isinstance(cell, StructuredCell):
        return fill_structured_cell_value(cell, node, "stored_state", "cached_state")
    elif isinstance(cell, Cell):
        return fill_simple_cell_value(cell, node, "stored_value", "cached_value")
    else:
        raise TypeError(type(cell))

def fill_cell_values(ctx, nodes, path=None):
    from ..highlevel import Cell, Transformer, Reactor, Link
    from ..core.structured_cell import StructuredCell
    manager = ctx._ctx._get_manager()
    try:
        manager.deactivate()
        for p in nodes:
            pp = path + p if path is not None else p
            child = ctx._children.get(pp)
            node = nodes[p]
            if child is None:
                assert node["type"] == "context"
                continue
            if "TEMP" in node:
                continue #not yet translated
            if isinstance(child, Transformer):
                transformer = child._get_tf()
                ###if transformer.status() == "OK":
                ###    node["in_equilibrium"] = True
                # Not nearly strong enough: upstream transformers may be engaged in long computation!
                input_name = node["INPUT"]
                inp = getattr(transformer, input_name)
                assert isinstance(inp, StructuredCell)
                fill_structured_cell_value(inp, node, "stored_state_input", "cached_state_input")
                fill_simple_cell_value(transformer.code, node, "code", "cached_code")
                if node["with_result"]:
                    result_name = node["RESULT"]
                    result = getattr(transformer, result_name, None)
                    if result is not None:
                        assert isinstance(result, StructuredCell)
                        fill_structured_cell_value(result, node, None, "cached_state_result")
            elif isinstance(child, Reactor):
                reactor = child._get_rc()
                io_name = node["IO"]
                io = getattr(reactor, io_name)
                assert isinstance(io, StructuredCell)
                fill_structured_cell_value(io, node, "stored_state_io", "cached_state_io")
                fill_simple_cell_value(reactor.code_start, node, "code_start", "cached_code_start")
                fill_simple_cell_value(reactor.code_update, node, "code_update", "cached_code_update")
                fill_simple_cell_value(reactor.code_stop, node, "code_stop", "cached_code_stop")
            elif isinstance(child, Cell):
                assert node["type"] == "cell", (pp, node["type"])
                cell = child._get_cell()
                try:
                    fill_cell_value(cell, node)
                except TypeError as e:
                    raise TypeError(p, node)
            elif isinstance(child, Link):
                continue
            else:
                raise TypeError(p, type(child))
    finally:
        manager.activate(only_macros=False)
