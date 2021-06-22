from copy import deepcopy
from numpy import e, isin
from ..core import cell, \
 transformer, context, StructuredCell

def translate_py_transformer(
        node, root, namespace, inchannels, outchannels,
        *, ipy_template, py_bridge
    ):
    from .translate import set_structured_cell_from_checksum
    from ..highlevel.Environment import Environment
    #TODO: simple translation, without a structured cell

    assert not (ipy_template is not None and py_bridge is not None)

    env0 = Environment(None)
    env0._load(node.get("environment"))
    env = env0._to_lowlevel()

    inchannels = [ic for ic in inchannels if ic[0] != "code"]

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
    for pin in list(node["pins"].keys()):
        pin_cell_name = pin + "_PIN"
        celltype = node["pins"][pin].get("celltype")
        if celltype is None:
            if pin.endswith("_SCHEMA"):
                celltype = "plain"
            else:
                celltype = "mixed"
        if celltype == "silk":
            celltype = "mixed"
        assert pin_cell_name not in all_inchannels
        assert pin_cell_name not in node["pins"]
        pin_cell = cell(celltype)
        cell_setattr(node, ctx, pin_cell_name, pin_cell)
        pin_cells[pin] = pin_cell

    interchannels = [as_tuple(pin) for pin in node["pins"]]
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
        namespace[path, "target"] = inp.inchannels[inchannel], node

    assert result_name not in node["pins"] #should have been checked by highlevel
    all_pins = {}
    for pinname, pin in node["pins"].items():
        p = {"io": "input"}
        p.update(pin)
        all_pins[pinname] = p
    all_pins[result_name] = {"io": "output", "celltype": "mixed"}
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
    ctx.tf = transformer(all_pins)
    if node["debug"]:
        ctx.tf.python_debug = True
    if node.get("compiled_debug"):
        ctx.tf.debug = True
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
    """
    print("INP CHECKSUM", inp_checksum)
    from ..core.context import Context
    print("INP VALUE", Context(toplevel=True)._get_manager().resolve(inp_checksum["auth"]))
    """

    set_structured_cell_from_checksum(inp, inp_checksum)
    namespace[node["path"] + ("code",), "target"] = ctx.code, node
    namespace[node["path"] + ("code",), "source"] = ctx.code, node

    for pin in list(node["pins"].keys()):
        target = ctx.tf.get_pin(pin)
        pin_cell = pin_cells[pin]
        inp.outchannels[(pin,)].connect(pin_cell)
        pin_cell.connect(target)

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

    if env is not None:
        ctx.tf.env = env

    namespace[node["path"], "target"] = inp, node
    namespace[node["path"], "source"] = result, node

from .util import get_path, as_tuple, build_structured_cell, cell_setattr
from .convert_checksum_dict import convert_checksum_dict