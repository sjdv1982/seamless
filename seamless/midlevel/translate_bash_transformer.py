import os, json
from copy import deepcopy
from seamless.core import cell, transformer, context
from ..metalevel.stdgraph import load as load_stdgraph


def translate_bash_transformer(
        node, root, namespace, inchannels, outchannels,
        *, has_meta_connection
    ):
    from .translate import set_structured_cell_from_checksum
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
            node, root, namespace, inchannels, outchannels,
            has_meta_connection = has_meta_connection,
            env=env, 
            docker_image=docker_image, docker_options=docker_options
        )


    inchannels = [ic for ic in inchannels if ic[0] != "code"]

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

    pins = node["pins"].copy()
    pins["bashcode"] = {"celltype": "text"}
    pins["pins_"] = {"celltype": "plain"}
    ctx.pins = cell("plain").set(list(pins.keys()))

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
        namespace[path, "target"] = inp.inchannels[inchannel], node

    assert result_name not in pins #should have been checked by highlevel
    all_pins = {}
    for pinname, pin in pins.items():
        p = {"io": "input"}
        p.update(pin)
        all_pins[pinname] = p
    all_pins[result_name] = {"io": "output"}
    if node["SCHEMA"]:
        raise NotImplementedError
        all_pins[node["SCHEMA"]] = {
            "io": "input", "transfer_mode": "json",
            "access_mode": "json", "content_type": "json"
        }
    ctx.tf = transformer(all_pins)
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
    set_structured_cell_from_checksum(inp, inp_checksum)

    ctx.executor_code = sctx.executor_code.cell()
    ctx.executor_code.connect(ctx.tf.code)

    namespace[node["path"] + ("code",), "target"] = ctx.code, node
    namespace[node["path"] + ("code",), "source"] = ctx.code, node

    for pinname, pin in node["pins"].items():
        target = ctx.tf.get_pin(pinname)
        celltype = pin.get("celltype", "mixed")
        if celltype == "code":
            celltype = "text"
        intermediate_cell = cell(celltype)
        cell_setattr(node, ctx, pin_intermediate[pinname], intermediate_cell)
        inp.outchannels[(pinname,)].connect(intermediate_cell)
        intermediate_cell.connect(target)

    meta = deepcopy(node.get("meta", {}))
    meta["transformer_type"] = "bash"
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