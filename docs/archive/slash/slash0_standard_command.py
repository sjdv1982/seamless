def make_cmd_params(command, nodes, env, sourcehash):
    inputs = {}
    outputs = []
    files = [] #to be monitored
    refs = []
    output_refs = []
    params = {
        "lineno": command["cmd"]["lineno"],
        "source": command["cmd"]["source"],
        "sourcehash": sourcehash,
        "refs": refs,
        "output_refs": output_refs,
        "inputs": inputs,
        "outputs": outputs,
        "files": files,
    }
    for noderef in command["noderefs"]:
        if noderef["type"] == "file":
            name = noderef["value"]
            if name not in files:
                files.append(name)
            refs.append(noderef)
        elif noderef["type"] == "doc" and noderef["index"] == -1:
            refs.append(None)
        elif noderef["type"] in ("doc", "variable"):
            node = nodes[noderef["type"]][noderef["index"]]
            name = node["name"]
            inputs[name] = noderef["type"]
            refs.append(name)
        elif noderef["type"] == "env":
            envname = nodes["env"][noderef["index"]]["name"]
            refs.append({"type": "env", "value": env[envname]})
        elif noderef["type"] == "varexp":
            subrefs = []
            for subnoderef in noderef["noderefs"]:
                if subnoderef["type"] == "variable":
                    node = nodes["variable"][subnoderef["index"]]
                    name = node["name"]
                    subrefs.append(name)
                    inputs[name] = "variable"
                elif subnoderef["type"] == "env":
                    envname = nodes["env"][subnoderef["index"]]["name"]
                    subrefs.append("$" + envname)
            ref = {"type": "varexp", "value": noderef["value"], "refs": subrefs}
            refs.append(ref)
        else:
            raise ValueError(command["cmd"]["source"], noderef["type"])
    for output in command["outputs"]:
        type_ = output["type"]
        noderef = output["noderef"]
        assert noderef["type"] == "doc"
        if noderef["index"] == -1:
            output_refs.append({"type": type_, "name": None})
        else:
            node = nodes["doc"][noderef["index"]]
            name = node["name"]
            if name not in outputs:
                outputs.append(name)
            output_refs.append({"type": type_, "name": name})
    capture = command.get("capture", None)
    if capture is not None:
        assert capture["type"] == "context"
        type_ = "capture"
        if capture["index"] == -1:
            output_refs.append({"type": type_, "name": None})
        else:
            node = nodes["context"][capture["index"]]
            name = node["name"]
            outputs.append(name)
            output_refs.append({"type": type_, "name": name})

    pragma = command.get("pragma", None)
    if pragma is not None:
        params["pragma"] = pragma
    params["command"] = command["parsed"]
    return params
