from ..core.macro import macro

@macro(("text", "code", "slash-0"))
def slash0(ctx, code, extern_map = {}, **macro_args):
    import os
    from seamless import context, cell, reactor
    from seamless.core.cell import Cell
    from seamless.core.worker import ExportedInputPin, ExportedOutputPin
    from seamless.lib.filehash import filehash
    from seamless.slash.parse_slash0 import parse_slash0
    from seamless.slash.ast_slash0_validate import ast_slash0_validate
    from seamless.slash.slash0_standard_command import make_cmd_params
    #cell_cmd_start = seamless.cell(("text", "code", "python")).fromfile("cell-command-start.py")
    #cell_cmd = seamless.cell(("text", "code", "python")).fromfile("cell-command.py")
    cell_filehash = seamless.cell(("text", "code", "python")).fromfile("cell-filehash.py")
    cell_filehash_stop = seamless.cell(("text", "code", "python")).fromfile("cell-filehash-stop.py")
    ast = parse_slash0(code)
    symbols = ast_slash0_validate(ast)
    env = {}
    variables = {}
    docs = {}
    contexts = {}
    filehashes = 0


    def make_cmd_std(cmd_params):
        reactor_params = {}
        in_connections = []
        out_connections = []
        for file_ in cmd_params["files"]:
            fh = make_filehash(file_)
            filehashes += 1
            fhname = "filehash-%d" % filehashes
            ctx.setattr(fhname, fh)
            in_connections.append((fh, fhname))
        rc = reactor(reactor_params)
        for con in in_connections:
            pin = getattr(rc, con[1])
            con[0].connect(pin)
        for con in out_connections:
            pin = getattr(rc, con[0])
            pin.connect(con[1])
        return rc

    for node in ast["nodes"]["env"]:
        envname = node["name"]
        assert envname in os.environ, envname
        env[envname] = os.environ[envname]
    for node in ast["nodes"]["file"]:
        filename = node["name"]
        assert os.path.exists(filename), filename
    for node in ast["nodes"]["context"]:
        name = "ctx_" + node["name"]
        if node["is_json"]:
            c = cell("json")
        else:
            c = context()
        contexts[node["name"]] = c
        setattr(ctx, name, c)
    for node in ast["nodes"]["variable"]:
        name = "var_" + node["name"]
        c = cell("str")
        variables[node["name"]] = c
        setattr(ctx, name, c)
    for node in ast["nodes"]["doc"]:
        name = "doc-" + node["name"]
        c = cell("text")
        docs[node["name"]] = c
        setattr(ctx, name, c)
        origin = node["origin"]
        if origin == "intern":
            pass
        elif origin == "extern":
            raise NotImplementedError #c.set(...) using extern_mapping + macro_args
        elif origin == "input":
            pin = ExportedInputPin(c)
            setattr(ctx, node["name"], pin)
        else:
            raise ValueError(origin)

    nodes = ast["nodes"]
    for noderef in ast["exports"]:
        node_type = noderef["type"]
        node = nodes[node_type][noderef["index"]]
        name = node["name"]
        if node_type == "context":
            c = contexts[name]
            assert isinstance(c, Cell) #TODO: export static subcontexts
        elif node_type == "variable":
            c = variables[name]
        elif node_type == "doc":
            c = docs[name]
        pin = ExportedOutputPin(c)
        setattr(ctx, name, pin)
    for command in ast["commands"]:
        source = command["cmd"]["source"]
        sourcehash = hex(hash(source))[2:]
        cmd_type = command["cmd"]["command"]
        if cmd_type == "standard":
            cmd_params = make_cmd_params(command, nodes, env)
            make_cmd_std(cmd_params)
        else:
            raise NotImplementedError(cmd_type)
#TODO: file nodes!
