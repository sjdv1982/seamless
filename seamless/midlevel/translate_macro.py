from seamless.core import cell, path as core_path, \
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
        elif pin["io"] in ("input", "output", "edit"):
            pin_cell_name = pinname
        else:
            raise ValueError((pin["io"], pinname))
        pin_hash_pattern = pin.get("hash_pattern")
        celltype = pin.get("celltype", "mixed")
        if celltype == "mixed":
            pin_cell = cell(celltype, hash_pattern=pin_hash_pattern)
        else:
            pin_cell = cell(celltype)
        cell_setattr(node, ctx, pin_cell_name, pin_cell)
        pin_cells[pinname] = pin_cell
        if pin["io"] != "parameter":
            pin_mpaths0[pinname] = (pin["io"] in ("input", "edit"))

    mount = node.get("mount", {})
    param = None
    if len(interchannels):
        param, param_ctx = build_structured_cell(
            ctx, param_name, param_inchannels, interchannels,
            return_context=True,
            fingertip_no_remote=False,
            fingertip_no_recompute=False,
            hash_pattern={"*": "#"}
        )

        setattr(ctx, param_name, param)
        namespace[node["path"] + ("SCHEMA",), "source"] = param.schema, node
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
    if node.get("elision"):
        ctx.macro.allow_elision = True

    elision = {
        "macro": ctx.macro,
        "input_cells": {},
        "output_cells": {}
    }
    for pinname in pin_mpaths0:
        is_input = pin_mpaths0[pinname]
        pin_mpath = getattr(core_path(ctx.macro.ctx), pinname)
        pin_cell = pin_cells[pinname]
        if is_input:
            if node["pins"][pinname]["io"] == "edit":
                pin_cell.bilink(pin_mpath)
            else:
                pin_cell.connect(pin_mpath)
                elision["input_cells"][pin_cell] = pin_mpath
        else:
            pin_mpath.connect(pin_cell)
            elision["output_cells"][pin_cell] = pin_mpath
    ctx._get_manager().set_elision(**elision)

    ctx.code = cell("macro")
    if "code" in mount:
        ctx.code.mount(**mount["code"])

    ctx.code.connect(ctx.macro.code)
    checksum = node.get("checksum", {})
    if "code" in checksum:
        ctx.code._set_checksum(checksum["code"], initial=True)
    if param is not None:
        param_checksum = convert_checksum_dict(checksum, "param")
        set_structured_cell_from_checksum(param, param_checksum)
    namespace[node["path"] + ("code",), "target"] = ctx.code, node
    namespace[node["path"] + ("code",), "source"] = ctx.code, node

    for pinname in node["pins"]:
        path = node["path"] + as_tuple(pinname)
        pin = node["pins"][pinname]
        if pin["io"] == "parameter":
            pinname2 = as_tuple(pinname)
            if pinname2 in inchannels:
                namespace[path, "target"] = param.inchannels[pinname], node
            target = getattr(ctx.macro, pinname)
            assert target is not None, pinname
            pin_cell = pin_cells[pinname]
            param.outchannels[pinname2].connect(pin_cell)
            pin_cell.connect(target)
        elif pin["io"] == "edit":
            namespace[path, "edit"] = pin_cells[pinname], node
        else:
            cmode = "target" if pin["io"] == "input" else "source"
            namespace[path, cmode] = pin_cells[pinname], node





from .util import get_path, as_tuple, build_structured_cell, cell_setattr
from .convert_checksum_dict import convert_checksum_dict