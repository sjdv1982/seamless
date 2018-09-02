from copy import deepcopy

def extract(nodes, connections):
    topology = []
    values = {}
    cached_values = {}
    for path0, node in nodes.items():
        path = ".".join(path0)
        nodetype = node["type"]
        result = deepcopy(node)
        if nodetype == "cell":
            value = result.pop("value", None)
            if value is not None:
                values[path] = value
            cached_value = result.pop("cached_value", None)
            if cached_value is not None:
                cached_values[path] = cached_value
        elif nodetype == "transformer":
            if "values" in result:
                v = {".".join(k):v for k,v in result["values"].items()}
                result["values"] = v
        topology.append(result)
    topology += connections
    return topology, values, cached_values
