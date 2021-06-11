import sys

def pretranslate(ctx, graph):
    assert isinstance(ctx, Context)
    nodes, connections = graph["nodes"], graph["connections"]
    libinstances = []
    for node in nodes:
        if node["type"] == "libinstance":
             path = tuple(node["path"])
             libinstances.append(path)
    if not len(libinstances):
        return graph
    nodedict = {tuple(node["path"]): node for node in nodes}
    overlay_nodedict = {}
    overlay_connections = []
    for path in libinstances:
        libinstance = LibInstance(ctx, path=path)
        result = libinstance._run()
        if libinstance.exception is not None:
            continue
        curr_graph, curr_nodes, curr_connections = result
        path2 = path + ("ctx",)
        for nodepath, node in curr_nodes.items():
            overlay_nodedict[nodepath] = node
        overlay_connections += curr_connections
        for node in curr_graph["nodes"]:            
            p = tuple(node["path"])
            nodepath = path2 + p
            node["path"] = nodepath
            overlay_nodedict[nodepath] = node
            """
            con = {
                "source": path,
                "target": nodepath,
                "type": "virtual",
            }
            overlay_connections.append(con)
            """
        for con in curr_graph["connections"]:
            con["source"] = path2 + tuple(con["source"])
            con["target"] = path2 + tuple(con["target"])
            overlay_connections.append(con)
    runtime_graph_nodedict = overlay_nodedict.copy()
    for nodename, node in nodedict.items():
        if nodename in libinstances:
            continue
        overlay_node = overlay_nodedict.get(nodename)
        if overlay_node is not None:
            newnode = node.copy()
            newnode.update(overlay_node)
            if "checksum" in overlay_node:
                if overlay_node["checksum"] is None:
                    newnode.pop("checksum")
            runtime_graph_nodedict[nodename] = newnode
        else:
            runtime_graph_nodedict[nodename] = node
    for path in libinstances:
        runtime_graph_nodedict[path] = {
            "type": "context",
            "path": path,
        }
        path2 = path + ("ctx",)
        runtime_graph_nodedict[path2] = {
            "type": "context",
            "path": path2,
        }
    runtime_graph_nodes = [
        v for k,v in sorted(runtime_graph_nodedict.items(),
        key=lambda kv: kv[0])
    ]
    runtime_graph_connections = connections + overlay_connections
    runtime_graph = {
        "nodes": runtime_graph_nodes,
        "connections": runtime_graph_connections,
        "params": graph["params"],
        "lib": graph["lib"],
    }
    return runtime_graph


from ..highlevel.Context import Context, Graph
from ..highlevel.library.libinstance import LibInstance
from ..highlevel.assign import under_libinstance_control