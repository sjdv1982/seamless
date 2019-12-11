def pretranslate(ctx, graph):
    assert isinstance(ctx, Context)
    nodes, connections = graph["nodes"], graph["connections"]
    libmacros = []
    for node in nodes:
        if node["type"] == "libmacro":
             path = tuple(node["path"])
             libmacros.append(path)
    if not len(libmacros):
        return graph
    nodedict = {tuple(node["path"]): node for node in nodes}
    overlay_nodedict = {}
    overlay_connections = []    
    for path in libmacros:
        libmacro = LibMacro(ctx, path=path)
        result = libmacro._run()
        curr_graph, curr_nodes, curr_connections = result
        path2 = path + ("ctx",)
        for nodepath, node in curr_nodes.items():
            overlay_nodedict[nodepath] = node
        overlay_connections += curr_connections
        for node in curr_graph["nodes"]:
            nodepath = path2 + tuple(node["path"])
            node["path"] = nodepath
            overlay_nodedict[nodepath] = node
        for con in curr_graph["connections"]:
            con["source"] = path2 + tuple(con["source"])
            con["target"] = path2 + tuple(con["target"])
            overlay_connections.append(con)        
    libmacro_nodedict = overlay_nodedict.copy()
    for nodename, node in nodedict.items():
        if nodename in libmacros:
            continue
        overlay_node = overlay_nodedict.get(nodename)
        if overlay_node is not None:
            newnode = node.copy()
            newnode.update(overlay_node)
            if "checksum" in overlay_node:
                if overlay_node["checksum"] is None:
                    newnode.pop("checksum")
            libmacro_nodedict[nodename] = newnode
        else:
            libmacro_nodedict[nodename] = node
    for path in libmacros:
        libmacro_nodedict[path] = {
            "type": "context",
            "path": path,
        } 
        path2 = path + ("ctx",)
        libmacro_nodedict[path2] = {
            "type": "context",
            "path": path2,
        } 
    libmacro_nodes = [
        v for k,v in sorted(libmacro_nodedict.items(), 
        key=lambda kv: kv[0])
    ]
    libmacro_connections = connections + overlay_connections
    libmacro_graph = {
        "nodes": libmacro_nodes, 
        "connections": libmacro_connections, 
        "params": graph["params"],
        "lib": graph["lib"],
    }
    return libmacro_graph
    

from ..highlevel.Context import Context, Graph
from ..highlevel.library.libmacro import LibMacro
from ..highlevel.assign import under_libmacro_control