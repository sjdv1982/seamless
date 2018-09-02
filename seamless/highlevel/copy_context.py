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

def assign_context(ctx, new_nodes, new_connections, path):
    from .Context import Context
    from .Cell import Cell
    from .Transformer import Transformer
    assert isinstance(ctx, Context)
    nodes, connections = ctx._graph
    for p in list(nodes.keys()):
        if p[:len(path)] == path:
            nodes.pop(p)
    for con in list(connections):
        source, target = con["source"], con["target"]
        if source[:len(path)] != path:
            continue
        if target[:len(path)] != path:
            continue
        connections.pop(con)
    ctx._graph[0][path] = {
        "path": path,
        "type": "context"
    }
    new_nodes = deepcopy(new_nodes)
    new_connections = deepcopy(new_connections)
    for p, node in new_nodes.items():
        pp = path + p
        node["path"] = pp
        nodes[pp] = node
        nodetype = node["type"]
        if nodetype == "cell":
            Cell(ctx, pp)
        elif nodetype == "transformer":
            Transformer(ctx, pp)
        elif nodetype == "context":
            pass
        else:
            raise TypeError(nodetype)
    for con in new_connections:
        con["source"] = path + con["source"]
        con["target"] = path + con["target"]
        connections.append(con)

def fill_cell_values(ctx, nodes, path=None):
    from .Cell import Cell
    from .Transformer import Transformer
    from ..core.structured_cell import StructuredCell
    manager = ctx._ctx._get_manager()
    try:
        manager.deactivate()
        for p in nodes:
            pp = path + p if path is not None else p
            child = ctx._children.get(pp)
            node = nodes[pp]
            if isinstance(child, Transformer):
                transformer = child._get_tf()
                if transformer.status() == "OK":
                    node["in_equilibrium"] = True
                continue
            if not isinstance(child, Cell):
                continue
            assert node["type"] == "cell", (pp, node["type"])
            cell = child._get_cell()
            if cell._authoritative:
                node["value"] = child.value
                node.pop("cached_value", None)
            else:
                node["cached_value"] = child.value
                node.pop("value", None)
    finally:
        manager.activate(only_macros=False)
