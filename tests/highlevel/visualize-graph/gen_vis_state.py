
rnodes = []
rconnections = []
path_to_id = {}


graph = graph.unsilk
state = state.unsilk

color_mapping = {
    1: "red",
    2: "orange",
    3: "yellow",
    4: "green",
    5: "blue",
}

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
    else: # TODO: libmacro, macro, reactor
        continue

    color = 5
    for subpath in paths:
        subpath2 = ".".join(subpath)
        status = state[subpath2 + ".status"]
        if status == "Status: OK":
            continue
        elif status.startswith("Status: executing"):
            color = min([color, 4])
        elif status.startswith("Status: pending"):
            color = min([color, 3])
        elif status.startswith("Status: upstream"):
            color = min([color, 2])
        else:
            color = 1
    rnode["color"] = color_mapping[color]
    rnodes.append(rnode)
    path_to_id[path] = rnode["id"]

for connection in graph["connections"]:
    rcon = {"type": connection["type"]}
    if connection["type"] == "link":
        source, target = connection["first"], connection["second"]
    else:
        source, target = connection["source"], connection["target"]
    
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
