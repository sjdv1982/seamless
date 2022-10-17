from copy import deepcopy
from seamless.core import cell, transformer, context
from ..metalevel.stdgraph import load as load_stdgraph
from ..core.cache.buffer_cache import empty_dict_checksum

def translate_bashdocker_transformer(
    node, root, namespace, 
    node_pins, inchannels, outchannels, 
    deep_inchannels, deep_pins,
    *, 
    docker_image, docker_options, has_meta_connection, env
):

    sctx = load_stdgraph("bashdocker_transformer")

    from .translate import set_structured_cell_from_checksum

    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    ctx = context(toplevel=False)
    setattr(parent, name, ctx)

    result_name = node["RESULT"]
    input_name = node["INPUT"]
    result_cell_name = result_name + "_CELL"
    forbidden = [result_name, result_cell_name, "docker_command", "docker_image_", "docker_options", "pins_"]
    pin_intermediate = {}
    for pin in list(node_pins.keys()) + list(deep_pins.keys()):
        pin_intermediate[pin] = input_name + "_PIN_" + pin
        forbidden.append(pin_intermediate[pin])
    for c in inchannels:
        assert (not len(c)) or c[0] not in forbidden #should have been checked by highlevel

    pins = node_pins.copy()
    pins["docker_command"] = {"celltype": "text"}
    pins["docker_image_"] = {"celltype": "str"}
    pins["docker_options"] = {"celltype": "plain"}
    pins["pins_"] = {"celltype": "plain"}
    pins0 = list(pins.keys())
    ctx.pins = cell("plain").set(pins0 + list(deep_pins.keys()))

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
            cell_setattr(node, ctx, pinname + "_CHECKSUM", pin_cell2)
            pin_cell3 = cell("plain")
            cell_setattr(node, ctx, pinname + "_CHECKSUM2", pin_cell3)
            pin_cell2.connect(pin_cell3)
            pin_cell3.connect(inp.inchannels[inchannel])
            namespace[path, "target"] = pin_cell2, node
        else:
            namespace[path, "target"] = inp.inchannels[inchannel], node

    assert result_name not in pins #should have been checked by highlevel


    pin_cells = {}
    pin_celltypes = {}
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
        pin_celltypes[pin] = celltype
        pin_cell = cell(celltype)
        pin_cell._hash_pattern = hash_pattern
        cell_setattr(node, ctx, pin_intermediate[pin], pin_cell)
        pin_cells[pin] = pin_cell

    all_pins = {}
    for pinname, pin in pins.items():
        p = {"io": "input"}
        p.update(pin)
        celltype = pin_celltypes.get(pinname)
        if celltype is not None:
            p["celltype"] = celltype
        all_pins[pinname] = p
    all_pins[result_name] = {"io": "output"}
    if node["SCHEMA"]:
        raise NotImplementedError
        all_pins[node["SCHEMA"]] = {
            "io": "input", "transfer_mode": "json",
            "access_mode": "json", "content_type": "json"
        }
    all_pins.update(deep_pins)
    ctx.tf = transformer(all_pins)
    ctx.code = cell("text")
    if "code" in mount:
        ctx.code.mount(**mount["code"])

    ctx.pins.connect(ctx.tf.pins_)
    ctx.tf.docker_image_.cell().set(docker_image)
    ctx.tf.docker_options.cell().set(docker_options)
    ctx.code.connect(ctx.tf.docker_command)
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

    meta = deepcopy(node.get("meta", {}))
    meta["transformer_type"] = "bashdocker"
    ctx.tf.meta = meta
    if has_meta_connection:
        ctx.meta = cell("plain")
        ctx.meta.connect(ctx.tf.META)
        namespace[node["path"] + ("meta",), "target"] = ctx.meta, node    

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

from .util import get_path, build_structured_cell, cell_setattr
from ..util import as_tuple
from .convert_checksum_dict import convert_checksum_dict