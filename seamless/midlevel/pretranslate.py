from copy import deepcopy
import sys

def pretranslate(ctx, graph, libinstance_nodes={},prev_overlay_nodes={}):
    assert isinstance(ctx, Context)
    nodes, connections = graph["nodes"], graph["connections"]
    graph_lib = deepcopy(graph["lib"])
    graph_params = deepcopy(graph["params"])
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
    has_libinstance_nodes = False
    extra_nodes = prev_overlay_nodes.copy()
    extra_nodes.update(libinstance_nodes)
    if not extra_nodes:
        extra_nodes = None
    for path in libinstances:
        libinstance = LibInstance(
            ctx, path=path, 
            extra_nodes=extra_nodes,
        )
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
            """
            con = {
                "source": path,
                "target": nodepath,
                "type": "virtual",
            }
            overlay_connections.append(con)
            """
            if node["type"] == "libinstance":
                has_libinstance_nodes = True
                if libinstance_nodes is None:
                    libinstance_nodes = {}
                # from assign.py . TODO: integrate
                nodelib = ctx._graph.lib[tuple(node["libpath"])]
                for argname, arg in list(node["arguments"].items()):
                    param = nodelib["params"][argname]
                    if param["type"] in ("cell", "context"):
                        if isinstance(arg, tuple):
                            arg = list(arg)
                        if not isinstance(arg, list):
                            arg = [arg]
                        arg = list(path2) + arg
                    elif param["type"] == "celldict":
                        for k,v in arg.items():
                            if isinstance(v, tuple):
                                v = list(v)
                            if not isinstance(v, list):
                                v = [v]
                            v = list(path2) + v
                    node["arguments"][argname] = arg
                libinstance_nodes[node["path"]] = node
        for con in curr_graph["connections"]:
            con["source"] = path2 + tuple(con["source"])
            con["target"] = path2 + tuple(con["target"])

        for node in curr_graph["nodes"]:   
            if node["type"] == "libinstance":
                continue
            overlay_nodedict[node["path"]] = node
        if has_libinstance_nodes:
            sub_runtime_graph = pretranslate(
                ctx, curr_graph, 
                libinstance_nodes=libinstance_nodes,
                prev_overlay_nodes=overlay_nodedict
            )
            for node in sub_runtime_graph["nodes"]:
                overlay_nodedict[node["path"]] = node
            overlay_connections += sub_runtime_graph["connections"]
            graph_lib += sub_runtime_graph["lib"]
            graph_params.update(sub_runtime_graph["params"])
        for con in curr_graph["connections"]:
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
    # eliminate duplicates
    con_ids = set()
    cons = []
    for con in runtime_graph_connections:
        idcon = id(con)
        if idcon in con_ids:
            continue
        cons.append(con)
        con_ids.add(idcon)
    runtime_graph_connections = cons
    
    runtime_graph = {
        "nodes": runtime_graph_nodes,
        "connections": runtime_graph_connections,
        "params": graph_params,
        "lib": graph_lib,
    }
    return runtime_graph


from ..highlevel.Context import Context, Graph
from ..highlevel.library.libinstance import LibInstance
from ..highlevel.assign import under_libinstance_control