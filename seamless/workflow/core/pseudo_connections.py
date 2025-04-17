def set_pseudo_connections(ctx, path, pseudo_connections):
    if ctx is None:
        return
    if not pseudo_connections:
        return
    from ..highlevel.Context import Context

    assert isinstance(ctx, Context)
    connections = []
    for source, target in pseudo_connections:
        strip = 1
        head = source[0]
        while head.startswith("."):
            head = head[1:]
            strip += 1
        source = path[:-strip] + (head,) + tuple(source[1:])

        strip = 1
        head = target[0]
        while head.startswith("."):
            head = head[1:]
            strip += 1
        target = path[:-strip] + (head,) + tuple(target[1:])

        con = {"source": source, "target": target, "type": "connection"}
        connections.append(con)
    ctx._runtime_graph.connections[:] = ctx._runtime_graph.connections + connections
