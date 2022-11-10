import textwrap

rnodes = []
rconnections = []
path_to_id = {}

status = status_

color_mapping = {
    1: "red",
    2: "orange",
    3: "yellow",
    4: "forestgreen",
    5: "royalblue",
}

libnodes = [tuple(node["path"]) for node in graph["lib"]]

for node in graph["nodes"]:
    path = tuple(node["path"])
    path2 = ".".join(path)
    rnode = {"name": path2, "type": node["type"], "id": len(rnodes)}
    if node["type"] == "cell":
        paths = [path]
    elif node["type"] == "transformer":
        paths = [
            path,
            path + (node["INPUT"],),
        ]
    elif node["type"] == "reactor":
        continue # TODO
    elif node["type"] == "macro":
        paths = [path]
    elif node["type"] == "context":
        continue
    elif node["type"] == "module":
        continue
    else: 
        raise Exception(node["type"])

    color = 5
    cstate = ""
    any_state = False
    for subpath in paths:
        subpath2 = ".".join(subpath)
        spath = subpath2 + ".status"
        if spath not in status:
            continue
        any_state = True
        state = status[spath]
        if state is None:
            state = ""
        h = "*tf*: "
        if state.startswith(h):
            state = state[len(h):]
        if len(state.split()) > 2:
            if subpath != path:
                cstate += "*** " + subpath2 + " ***\n"
            cstate += "*** status ***\n"
            cstate += state
            cstate += "\n" + "*" * 50 + "\n\n"
        if state == "Status: OK":
            continue
        elif state.startswith("Status: executing"):
            color = min([color, 4])
        elif state.startswith("Status: pending"):
            color = min([color, 3])
        elif state.startswith("Status: upstream"):
            color = min([color, 2])
        else:
            color = 1
        exc = status.get(subpath2 + ".exception", "")
        if exc is None:
            exc = ""
        if len(exc.split()) > 2:
            if subpath != path:
                cstate += "*** " + subpath2 + " ***\n"
            cstate += "*** exception ***\n"
            exc2 = []
            for l in exc.splitlines():
                exc2.extend(textwrap.wrap(l))
            exc = "\n".join(exc2)
            cstate += exc
            cstate += "\n" + "*" * 50 + "\n\n"
    if any_state:
        rnode["color"] = color_mapping[color]
        if cstate:
            rnode["status"] = cstate
    else:
        rnode["color"] = "grey"
    rnodes.append(rnode)
    path_to_id[path] = rnode["id"]

for connection in graph["connections"]:
    rcon = {"type": connection["type"]}
    if connection["type"] == "link":
        source, target = connection["first"], connection["second"]
    elif connection["type"] == "connection":
        source, target = connection["source"], connection["target"]
    elif connection["type"] == "virtual":
        source, target = connection["source"], connection["target"]
        for path in source, target:
            path = tuple(path)
            if path not in path_to_id:
                path2 = ".".join(path)
                rnode = {"name": path2, "type": "virtual", "id": len(rnodes)}
                rnode["color"] = "grey"
                rnodes.append(rnode)
                path_to_id[path] = rnode["id"]

    source_id, target_id = None, None
    for n in range(len(source), 0, -1):
        path = tuple(source[:n])
        source_id = path_to_id.get(path)
        if source_id is not None:
            break
    for n in range(len(target), 0, -1):
        path = tuple(target[:n])
        target_id = path_to_id.get(path)
        if target_id is not None:
            break
    if source_id is None or target_id is None:
        continue
    rcon["source"] = source_id
    rcon["target"] = target_id
    rconnections.append(rcon)

result = {
    "nodes": rnodes,
    "connections": rconnections,
}
