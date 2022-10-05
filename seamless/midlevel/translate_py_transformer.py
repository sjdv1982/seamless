from copy import deepcopy
from ..core import cell, transformer, context

def translate_py_transformer(
        node, root, namespace, inchannels, outchannels,
        *, ipy_template, py_bridge, has_meta_connection
    ):
    from .translate import set_structured_cell_from_checksum
    from ..core.cache.buffer_cache import empty_dict_checksum
    from ..highlevel.Environment import Environment
    #TODO: simple translation, without a structured cell

    assert not (ipy_template is not None and py_bridge is not None)

    env0 = Environment(None)
    env0._load(node.get("environment"))
    env = env0._to_lowlevel()

    node_pins = deepcopy(node["pins"])
    deep_pins = {}
    for pinname,pin in list(node_pins.items()):
        if pin.get("celltype") in ("folder", "deepfolder", "deepcell"):
            if pin["celltype"] == "deepcell":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "#"},
                    "filesystem": {
                        "mode": "file",
                        "optional": True
                    },
                }
            elif pin["celltype"] == "deepfolder":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "##"},
                    "filesystem": {
                        "mode": "directory",
                        "optional": False
                    },
                }
            elif pin["celltype"] == "folder":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "##"},
                    "filesystem": {
                        "mode": "directory",
                        "optional": True
                    },
                }
            pin["io"] = "input"
            deep_pins[pinname] = pin
            node_pins.pop(pinname)
    deep_inchannels = [ic for ic in inchannels if ic[0] in deep_pins]
    inchannels = [ic for ic in inchannels if ic[0] != "code" and ic[0] not in deep_pins]

    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    ctx = context(toplevel=False)
    setattr(parent, name, ctx)

    result_name = node["RESULT"]
    result_cell_name = result_name + "_CELL"
    if node["language"] != "python":
        assert result_name == "result"
    input_name = node["INPUT"]
    for c in inchannels:
        assert (not len(c)) or c[0] not in (result_name, result_cell_name) #should have been checked by highlevel
    all_inchannels = set(inchannels)
    pin_cells = {}
    for pin in list(node_pins.keys()) + list(deep_pins.keys()):
        pin_cell_name = pin + "_PIN"
        hash_pattern = None
        if pin in deep_pins:
            celltype = deep_pins[pin]["celltype"]
            hash_pattern = deep_pins[pin]["hash_pattern"]
        else:
            celltype = node_pins[pin].get("celltype")
            if celltype is None or celltype == "default":
                if pin.endswith("_SCHEMA"):
                    celltype = "plain"
                else:
                    celltype = "mixed"
            if celltype == "silk":
                celltype = "mixed"
            if celltype == "checksum":
                celltype = "plain"
        assert pin_cell_name not in all_inchannels
        assert pin_cell_name not in node_pins
        pin_cell = cell(celltype)
        pin_cell._hash_pattern = hash_pattern
        cell_setattr(node, ctx, pin_cell_name, pin_cell)
        pin_cells[pin] = pin_cell

    interchannels = [as_tuple(pin) for pin in node_pins]
    mount = node.get("mount", {})
    inp, inp_ctx = build_structured_cell(
      ctx, input_name, inchannels, interchannels,
      fingertip_no_remote=node.get("fingertip_no_remote", False),
      fingertip_no_recompute=node.get("fingertip_no_recompute", False),
      hash_pattern= node.get("hash_pattern"),
      return_context=True
    )

    setattr(ctx, input_name, inp)
    namespace[node["path"] + ("SCHEMA",), "source"] = inp.schema, node
    if "input_schema" in mount:
        inp_ctx.schema.mount(**mount["input_schema"])
    for inchannel in inchannels:
        path = node["path"] + inchannel
        is_checksum = False
        if len(inchannel) == 1:            
            pinname = inchannel[0]
            pin = node_pins[pinname]
            if pin.get("celltype") == "checksum":
                is_checksum = True
        if is_checksum:
            pin_cell2 = cell("checksum")
            cell_setattr(node, ctx, pinname + "_CHECKSUM", pin_cell2)
            pin_cell3 = cell("plain")
            cell_setattr(node, ctx, pinname + "_CHECKSUM2", pin_cell3)
            pin_cell2.connect(pin_cell3)
            pin_cell3.connect(inp.inchannels[inchannel])
            namespace[path, "target"] = pin_cell2, node
        else:
            namespace[path, "target"] = inp.inchannels[inchannel], node
    for inchannel in deep_inchannels:
        path = node["path"] + inchannel
        pinname = inchannel[0]
        pin_cell = pin_cells[pinname]
        namespace[path, "target"] = pin_cell, node

    assert result_name not in node["pins"] #should have been checked by highlevel
    result_celltype = node.get("result_celltype", "structured")
    result_celltype2 = result_celltype
    if result_celltype in ("structured", "folder", "deepcell"):
        result_celltype2 = "mixed"
    all_pins = {}
    for pinname, pin in node_pins.items():
        p = {"io": "input"}
        p.update(pin)
        if p.get("celltype") == "default":
            p["celltype"] = "mixed"
        elif p.get("celltype") == "checksum":
            p["celltype"] = "plain"
        all_pins[pinname] = p
    result_pin = {
        "io": "output", 
        "celltype": result_celltype2
    }
    result_hash_pattern = None
    if result_celltype == "deepcell":
        result_hash_pattern = {"*": "#"}
    elif result_celltype == "folder":
        result_hash_pattern = {"*": "##"}
    if result_hash_pattern is not None:
        result_pin["hash_pattern"] = result_hash_pattern
    all_pins[result_name] = result_pin 
    if node["SCHEMA"]:
        all_pins[node["SCHEMA"]] = {
            "io": "input", "celltype": "mixed"
        }
    if py_bridge is not None: 
        for k in "code_", "bridge_parameters":
            if k in all_pins:
                msg = "Python bridge for {} cannot have a pin named '{}'".format(
                    "." + "".join(node["path"]), k 
                )
                raise ValueError(msg)
        all_pins.update({
            "code_": {
                "io": "input",
                "celltype": "text",
                "as": "code",
            },
            "bridge_parameters": {
                "io": "input",
                "celltype": "plain",
            },
        })
    all_pins.update(deep_pins)
    ctx.tf = transformer(all_pins)
    if node["language"] == "ipython" or ipy_template is not None:
        if env is None:
            env = {}
        if env.get("powers") is None:
            env["powers"] = []
        env["powers"] += ["ipython"]
    
    if ipy_template is not None or py_bridge is not None:
        ctx.code = cell("text")
    elif node["language"] == "ipython":
        ctx.code = cell("ipython")
    elif node["language"] == "python":
        ctx.code = cell("transformer")
    else:
        raise ValueError(node["language"]) # shouldn't happen

    if "code" in mount:
        ctx.code.mount(**mount["code"])

    if ipy_template is not None:        
        ipy_template_params = {
            "code_": {
                "io": "input",
                "celltype": "text",
                "as": "code",
            },
            "parameters": {
                "io": "input",
                "celltype": "plain",
            },
            "result": {
                "io": "output",
                "celltype": "ipython",
            }            
        }
        ctx.apply_ipy_template = transformer(ipy_template_params)
        ctx.ipy_template_code = cell("transformer").set(ipy_template[0])
        ctx.ipy_template_code.connect(ctx.apply_ipy_template.code)
        par = ipy_template[1]
        if par is None:
            par = {}
        ctx.apply_ipy_template.parameters.cell().set(par)
        tmpl_env = ipy_template[2]
        if tmpl_env is not None:
            tmpl_env2 = Environment()
            tmpl_env2._load(tmpl_env)
            ctx.apply_ipy_template.env = tmpl_env2._to_lowlevel()
        ctx.code.connect(ctx.apply_ipy_template.code_)
        ctx.ipy_code = cell("ipython")
        ctx.apply_ipy_template.result.connect(ctx.ipy_code)
        ctx.ipy_code.connect(ctx.tf.code)
    elif py_bridge is not None: 
        ctx.py_bridge_code = cell("transformer").set(py_bridge[0])
        ctx.py_bridge_code.connect(ctx.tf.code)
        ctx.code.connect(ctx.tf.code_)
        par = py_bridge[1]
        if par is None:
            par = {}
        ctx.tf.bridge_parameters.cell().set(par)
        bridge_env00 = py_bridge[2]
        if bridge_env00 is not None:
            bridge_env0 = Environment()
            bridge_env0._load(bridge_env00)
            bridge_env = bridge_env0._to_lowlevel()
            if env is None:
                env = {}
            if "powers" in bridge_env:
                if "powers" in env:
                    env["powers"] = env["powers"] + bridge_env["powers"]
                else:
                    env["powers"] = bridge_env["powers"]
            if "which" in bridge_env:
                if "which" in env:
                    env["which"] = env["which"] + bridge_env["which"]
                else:
                    env["which"] = bridge_env["which"]
            if "conda" in bridge_env:
                if "conda" in env:
                    for k in env["conda"]:
                        v = deepcopy(env["conda"][k])
                        if k in bridge_env["conda"]:
                            bv = deepcopy(bridge_env["conda"][k])
                            ok = True
                            if type(v) != type(bv):
                                ok = False
                            if isinstance(v, list):
                                v += bv
                            elif isinstance(v, dict):
                                v.update(bv)
                            else:
                                ok = False
                            if not ok:
                                raise TypeError(
                                    "Python bridge: cannot merge conda environments",
                                    "."+".".join(node["path"]), node["language"],
                                    k, type(v), type(bv)
                                )
    else:
        ctx.code.connect(ctx.tf.code)
    
    checksum = node.get("checksum", {})
    if "code" in checksum:
        ctx.code._set_checksum(checksum["code"], initial=True)
    inp_checksum = convert_checksum_dict(checksum, "input")
    if not len(node_pins): # no non-deepcell pins. Just to avoid errors.
        inp_checksum = {"auth": empty_dict_checksum}
    """
    print("INP CHECKSUM", inp_checksum)
    from ..core.context import Context
    print("INP VALUE", Context(toplevel=True)._get_manager().resolve(inp_checksum["auth"]))
    """

    set_structured_cell_from_checksum(inp, inp_checksum)
    namespace[node["path"] + ("code",), "target"] = ctx.code, node
    namespace[node["path"] + ("code",), "source"] = ctx.code, node

    for pin in list(node_pins.keys()):
        target = ctx.tf.get_pin(pin)
        pin_cell = pin_cells[pin]
        inp.outchannels[(pin,)].connect(pin_cell)
        pin_cell.connect(target)

    for pin in list(deep_pins.keys()):
        target = ctx.tf.get_pin(pin)
        pin_cell = pin_cells[pin]
        pin_cell.connect(target)

    if has_meta_connection:
        ctx.meta = cell("plain")
        ctx.meta.connect(ctx.tf.META)
        namespace[node["path"] + ("meta",), "target"] = ctx.meta, node    
    else:
        meta = node.get("meta")
        if meta is not None:
            ctx.tf.meta = meta

    if result_celltype == "structured":
        result, result_ctx = build_structured_cell(
            ctx, result_name, [()],
            outchannels,
            fingertip_no_remote=node.get("fingertip_no_remote", False),
            fingertip_no_recompute=node.get("fingertip_no_recompute", False),
            return_context=True
        )

        namespace[node["path"] + ("RESULTSCHEMA",), "source"] = result.schema, node
        if "result_schema" in mount:
            result_ctx.schema.mount(**mount["result_schema"])

        setattr(ctx, result_name, result)

        result_pin = ctx.tf.get_pin(result_name)
        result_cell = cell("mixed")
        cell_setattr(node, ctx, result_cell_name, result_cell)
        result_pin.connect(result_cell)
        result_cell.connect(result.inchannels[()])
        if node["SCHEMA"]:
            schema_pin = ctx.tf.get_pin(node["SCHEMA"])
            result.schema.connect(schema_pin)
        result_checksum = {}
        for k in checksum:
            if not k.startswith("result"):
                continue
            k2 = "value" if k == "result" else k[len("result_"):]
            result_checksum[k2] = checksum[k]
        set_structured_cell_from_checksum(result, result_checksum)
    else:
        result_pin = ctx.tf.get_pin(result_name)
        result_cell = cell(result_celltype2)
        result_cell._hash_pattern = result_hash_pattern
        cell_setattr(node, ctx, result_name, result_cell)
        result_pin.connect(result_cell)
        result = result_cell
        if checksum.get("result") is not None:
            result._set_checksum(checksum["result"], initial=True)

    if env is not None:
        ctx.tf.env = env

    namespace[node["path"], "target"] = inp, node
    namespace[node["path"], "source"] = result, node

from .util import get_path, build_structured_cell, cell_setattr
from ..util import as_tuple
from .convert_checksum_dict import convert_checksum_dict