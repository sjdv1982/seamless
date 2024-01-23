import os, json
from copy import deepcopy
from seamless.core import cell, transformer, context
from ..metalevel.stdgraph import load as load_stdgraph


def translate_bash_transformer(
        node, root, namespace, inchannels, outchannels,
        *, has_meta_connection
    ):
    from .translate import set_structured_cell_from_checksum
    from ..core.cache.buffer_cache import empty_dict_checksum
    from ..highlevel.Environment import Environment
    from ..core.environment import (
        validate_capabilities,
        validate_conda_environment,
        validate_docker
    )
    sctx = load_stdgraph("bash_transformer")

    env0 = Environment(None)
    env0._load(node.get("environment"))
    env = env0._to_lowlevel()

    is_docker_transformer = False
    if env is not None and env.get("docker") is not None:
        ok1 = validate_capabilities(env)[0]
        ok2 = validate_conda_environment(env)[0]
        ok3 = validate_docker(env)[0]
        if not (ok1 or ok2 or ok3):
            is_docker_transformer = True

    scratch = node.get("scratch", False)

    node_pins = deepcopy(node["pins"])
    deep_pins = {}
    for pinname,pin in list(node_pins.items()):
        pin.pop("subcelltype", None) # just to make sure...
        if pin.get("celltype") == "module":
            pin.clear()
            pin.update({
                "celltype": "plain",
                "subcelltype": "module"
            })
        elif pin.get("celltype") in ("folder", "deepfolder", "deepcell", "bytes"):
            if pin["celltype"] == "deepcell":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "#"},
                    "filesystem": {
                        "mode": "file",
                        "optional": False
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
            elif pin["celltype"] == "bytes":
                pin = {
                    "celltype": "bytes",
                    "hash_pattern": None,
                    "filesystem": {
                        "mode": "file",
                        "optional": True
                    },
                }

            pin["io"] = "input"
            deep_pins[pinname] = pin
            node_pins.pop(pinname)
    deep_inchannels = [ic for ic in inchannels if ic[0] in deep_pins]
    inchannels = [ic for ic in inchannels if ic[0] != "code" and ic[0] not in deep_pins]

    if is_docker_transformer:
        from .translate_bashdocker_transformer import translate_bashdocker_transformer
        docker = env.pop("docker")
        docker_image = docker["name"]
        docker_options = docker.get("options", {})
        # TODO: pass on version and checksum as well?
        if "powers" not in env:
            env["powers"] = []
        env["powers"].append("docker")
        return translate_bashdocker_transformer(
            node, root, namespace, 
            node_pins, inchannels, outchannels,
            deep_inchannels, deep_pins,
            has_meta_connection = has_meta_connection,
            env=env, 
            docker_image=docker_image, docker_options=docker_options
        )

    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    ctx = context(toplevel=False)
    setattr(parent, name, ctx)

    result_name = node["RESULT"]
    input_name = node["INPUT"]
    result_cell_name = result_name + "_CELL"
    forbidden = [result_name, result_cell_name, "bashcode", "pins_"]
    pin_intermediate = {}
    for pin in node["pins"].keys():
        pin_intermediate[pin] = input_name + "_PIN_" + pin
        forbidden.append(pin_intermediate[pin])
    for c in inchannels:
        assert (not len(c)) or c[0] not in forbidden #should have been checked by highlevel

    pins = node_pins.copy()
    pins["bashcode"] = {"celltype": "text"}
    pins["pins_"] = {"celltype": "plain"}
    pins_ = set(list(pins.keys()) + list(deep_pins.keys()))
    pins_ = sorted([pin for pin in pins_ if pin not in ("pins_", "bashcode")])
    ctx.pins = cell("plain").set(pins_)

    interchannels = [as_tuple(pin) for pin in pins]
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
            pin_cell2._scratch = True            
            cell_setattr(node, ctx, pinname + "_CHECKSUM", pin_cell2)
            pin_cell3 = cell("plain")
            pin_cell3._scratch = True
            cell_setattr(node, ctx, pinname + "_CHECKSUM2", pin_cell3)
            pin_cell2.connect(pin_cell3)
            pin_cell3.connect(inp.inchannels[inchannel])
            namespace[path, "target"] = pin_cell2, node
        else:
            namespace[path, "target"] = inp.inchannels[inchannel], node

    assert result_name not in pins #should have been checked by highlevel
    result_celltype = node.get("result_celltype", "structured")
    result_celltype2 = result_celltype
    if result_celltype in ("structured", "folder", "deepcell"):
        result_celltype2 = "mixed"
    all_pins = {}
    for pinname, pin in pins.items():
        p = {"io": "input"}
        p.update(pin)
        celltype = pin.get("celltype")
        if celltype is None or celltype == "default":
            if pinname.endswith("_SCHEMA"):
                celltype = "plain"
            else:
                celltype = "mixed"
        if celltype == "code":
            celltype = "text"
        if celltype == "checksum":
            celltype = "plain"
        p["celltype"] = celltype
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
        raise NotImplementedError
        all_pins[node["SCHEMA"]] = {
            "io": "input", "transfer_mode": "json",
            "access_mode": "json", "content_type": "json"
        }
    all_pins.update(deep_pins)
    ctx.tf = transformer(all_pins)
    ctx.tf._scratch = scratch
    if node.get("debug"):
        ctx.tf.debug = True
    ctx.code = cell("text")
    if "code" in mount:
        ctx.code.mount(**mount["code"])

    ctx.pins.connect(ctx.tf.pins_)
    ctx.code.connect(ctx.tf.bashcode)
    checksum = node.get("checksum", {})
    if "code" in checksum:
        ctx.code._set_checksum(checksum["code"], initial=True)
    inp_checksum = convert_checksum_dict(checksum, "input")
    if not len(node_pins): # no non-deepcell pins. Just to avoid errors.
        inp_checksum = {"auth": empty_dict_checksum}
    set_structured_cell_from_checksum(inp, inp_checksum)

    ctx.executor_code = sctx.executor_code.cell()
    ctx.executor_code.connect(ctx.tf.code)

    namespace[node["path"] + ("code",), "target"] = ctx.code, node
    namespace[node["path"] + ("code",), "source"] = ctx.code, node

    meta = deepcopy(node.get("meta", {}))
    meta["transformer_type"] = "bash"
    ctx.tf.meta = meta
    if has_meta_connection:
        ctx.meta = cell("plain")
        ctx.meta.connect(ctx.tf.META)
        namespace[node["path"] + ("meta",), "target"] = ctx.meta, node

    pin_cells = {}
    for pin in list(node_pins.keys()) + list(deep_pins.keys()):        
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
            if celltype == "code":
                celltype = "text"
        pin_cell = cell(celltype)
        if celltype != "plain" or node_pins[pin].get("subcelltype") != "module":
            pin_cell._scratch = True        
        pin_cell._hash_pattern = hash_pattern
        cell_setattr(node, ctx, pin_intermediate[pin], pin_cell)
        pin_cells[pin] = pin_cell

    for pin in list(node_pins.keys()):
        target = ctx.tf.get_pin(pin)
        intermediate_cell = pin_cells[pin]
        inp.outchannels[(pin,)].connect(intermediate_cell)
        intermediate_cell.connect(target)

    for inchannel in deep_inchannels:
        path = node["path"] + inchannel
        pinname = inchannel[0]
        pin_cell = pin_cells[pinname]
        target = ctx.tf.get_pin(pinname)
        pin_cell.connect(target)
        namespace[path, "target"] = pin_cell, node

    if result_celltype == "structured":
        result, result_ctx = build_structured_cell(
            ctx, result_name, [()],
            outchannels,
            fingertip_no_remote=node.get("fingertip_no_remote", False),
            fingertip_no_recompute=node.get("fingertip_no_recompute", False),
            return_context=True,
            scratch=True
        )
        namespace[node["path"] + ("RESULTSCHEMA",), "source"] = result.schema, node
        if "result_schema" in mount:
            result_ctx.schema.mount(**mount["result_schema"])

        setattr(ctx, result_name, result)

        result_pin = ctx.tf.get_pin(result_name)
        result_cell = cell("mixed")
        result_cell._scratch = True
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
        result_cell._scratch = True
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