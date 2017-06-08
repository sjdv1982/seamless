from ..core.macro import macro

@macro(("text", "code", "slash-0"), with_caching=True)
def slash0(ctx, code, extern_map = {}, **macro_args):
    import os, seamless, hashlib
    from seamless import context, cell, pythoncell, reactor, transformer
    from seamless.core.cell import Cell
    from seamless.core.worker import ExportedInputPin, ExportedOutputPin
    from seamless.lib.filehash import filehash
    from seamless.slash.parse_slash0 import parse_slash0
    from seamless.slash.ast_slash0_validate import ast_slash0_validate
    from seamless.slash.slash0_standard_command import make_cmd_params
    ctx.cell_cmd_std = seamless.pythoncell().fromfile("cell-command-standard.py")
    ast = parse_slash0(code)
    symbols = ast_slash0_validate(ast)
    env = {}
    variables = {}
    docs = {}
    contexts = {}
    filehashes = 0

    def make_cmd_std(cmd_params):
        nonlocal filehashes
        tf_params = {
            "PARAMS": {
                "pin": "input",
                "dtype": "json",
            },
        }
        in_connections = []
        out_connections = []
        for file_ in cmd_params["files"]:
            fh = filehash(file_)
            filehashes += 1
            fhname = "filehash_%d" % filehashes
            tf_params[fhname] = {
                "pin": "input",
                "dtype": "str"
            }
            fhname = "filehash_%d" % filehashes
            setattr(ctx, fhname, fh)
            in_connections.append((fh.filehash.cell(), fhname))
        for inp,typ in cmd_params["inputs"].items():
            if typ == "doc":
                dtype = "text"
                prefix = "doc_"
            elif typ == "variable":
                dtype = "str"
                prefix = "var_"
            else:
                raise TypeError((cmd_params["lineno"], cmd_params["source"], inp, typ)) #must be a bug
            tf_params[inp] = {
                "pin": "input",
                "dtype": dtype,
            }
            in_connections.append((ctx.CHILDREN[prefix + inp], inp))

        if len(cmd_params["outputs"]) > 1:
            raise NotImplementedError("Multiple outputs not yet implemented")

        for output in cmd_params["outputs"]:
            if hasattr(ctx, "ctx_" + output):
                dtype = "json"
                prefix = "ctx_"
            else:
                dtype = "text"
                prefix = "doc_"
            tf_params[output] = {
                "pin": "output",
                "dtype": dtype,
            } #TODO: in case of multiple outputs => single JSON cell + subcells (to be implemented)
            out_connections.append((output, ctx.CHILDREN[prefix + output]))

        tf = transformer(tf_params)
        tf.PARAMS.cell().set(cmd_params)
        for con in in_connections:
            pin = getattr(tf, con[1])
            con[0].connect(pin)
        for con in out_connections:
            pin = getattr(tf, con[0])
            pin.connect(con[1])
        ctx.cell_cmd_std.connect(tf.code)
        return tf

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
            c.resource.save_policy = 2
        else:
            c = context()
        contexts[node["name"]] = c
        setattr(ctx, name, c)
    for node in ast["nodes"]["variable"]:
        name = "var_" + node["name"]
        c = cell("str")
        c.resource.save_policy = 2
        variables[node["name"]] = c
        setattr(ctx, name, c)
        origin = node["origin"]
        if origin == "intern":
            pass #nothing to do
        elif origin == "extern":
            raise NotImplementedError #c.set(...) using extern_mapping + macro_args
        elif origin == "input":
            pin = ExportedInputPin(c)
            setattr(ctx, node["name"], pin)
        else:
            raise ValueError(origin)
    for node in ast["nodes"]["doc"]:
        name = "doc_" + node["name"]
        c = cell("text")
        c.resource.save_policy = 2
        docs[node["name"]] = c
        setattr(ctx, name, c)
        origin = node["origin"]
        if origin == "intern":
            pass #nothing to do
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
        sourcehash = hashlib.md5(source.encode("utf-8")).hexdigest()
        cmd_type = command["cmd"]["command"]
        if cmd_type == "standard":
            cmd_params = make_cmd_params(command, nodes, env, sourcehash)
            command_worker = make_cmd_std(cmd_params)
            name = "cmd-" + sourcehash
            setattr(ctx, name, command_worker)
            setattr(ctx, name +"-PARAMS", command_worker.PARAMS.cell())
        else:
            raise NotImplementedError(cmd_type)
#TODO: file nodes! (???)
