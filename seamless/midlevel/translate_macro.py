from seamless.core import cell, link, path as core_path, \
 macro, context, StructuredCell
from seamless.core.macro import Path

def translate_macro(node, root, namespace, inchannels, outchannels):
    from .translate import set_structured_cell_from_checksum

    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    ctx = context(toplevel=False)
    setattr(parent, name, ctx)

    param_name = node["PARAM"]
    all_inchannels = set(inchannels)
    param_inchannels = []
    interchannels = []
    pin_cells = {}
    pin_mpaths0 = {}
    for pinname in list(node["pins"].keys()):
        pin = node["pins"][pinname]
        if pin["io"] == "parameter":
            pin_cell_name = pinname + "_PARAM"
            assert pin_cell_name not in node["pins"]
            assert pin_cell_name not in all_inchannels
            pinname2 = as_tuple(pinname)
            interchannels.append(pinname2)
            if pinname2 in inchannels:
                param_inchannels.append(pinname2)           
        elif pin["io"] in ("input", "output"):
            pin_cell_name = pinname
        else:
            raise ValueError((pin["io"], pinname))        
        pin_cell = cell(pin.get("celltype", "mixed"))
        cell_setattr(node, ctx, pin_cell_name, pin_cell)
        pin_cells[pinname] = pin_cell
        if pin["io"] != "parameter":
            pin_mpaths0[pinname] = (pin["io"] == "input")
        
    mount = node.get("mount", {})    
    param, param_ctx = build_structured_cell(
      ctx, param_name, param_inchannels, interchannels,
      return_context=True,
      fingertip_no_remote=False,
      fingertip_no_recompute=False,
    )

    setattr(ctx, param_name, param)
    namespace[node["path"] + ("SCHEMA",), False] = param.schema, node    
    if "param_schema" in mount:
        param_ctx.schema.mount(**mount["param_schema"])

    param_pins = {}
    for pinname, pin in node["pins"].items():
        if pin["io"] != "parameter":
            continue
        p = {"io": "input"}
        p.update(pin)
        param_pins[pinname] = p
    ctx.macro = macro(param_pins)

    for pinname in pin_mpaths0:
        is_input = pin_mpaths0[pinname]
        pin_mpath = getattr(core_path(ctx.macro.ctx), pinname)
        pin_cell = pin_cells[pinname]
        if is_input:
            pin_cell.connect(pin_mpath)
        else:
            pin_mpath.connect(pin_cell)

    ctx.code = cell("macro")
    if "code" in mount:
        ctx.code.mount(**mount["code"])

    ctx.code.connect(ctx.macro.code)
    checksum = node.get("checksum", {})
    if "code" in checksum:
        ctx.code._set_checksum(checksum["code"], initial=True)
    param_checksum = {}
    for k in checksum:
        if k == "schema":
            param_checksum[k] = checksum[k]
            continue
        if not k.startswith("param"):
            continue
        k2 = "value" if k == "param" else k[len("param_"):]
        param_checksum[k2] = checksum[k]

    set_structured_cell_from_checksum(param, param_checksum)
    namespace[node["path"] + ("code",), True] = ctx.code, node
    namespace[node["path"] + ("code",), False] = ctx.code, node

    for pinname in node["pins"]:
        path = node["path"] + as_tuple(pinname)
        pin = node["pins"][pinname]
        if pin["io"] == "parameter":
            pinname2 = as_tuple(pinname)
            if pinname2 in inchannels:
                namespace[path, True] = param.inchannels[pinname], node
            target = getattr(ctx.macro, pinname)
            pin_cell = pin_cells[pinname]
            param.outchannels[pinname2].connect(pin_cell)
            pin_cell.connect(target)
        else:
            is_target = (pin["io"] == "input")
            namespace[path, is_target] = pin_cells[pinname], node





from .util import get_path, as_tuple, build_structured_cell, cell_setattr
