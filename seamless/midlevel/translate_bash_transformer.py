import os, json
from seamless.core import cell, transformer, context
from ..midlevel.StaticContext import StaticContext

import seamless
seamless_dir = os.path.dirname(seamless.__file__)
graphfile = os.path.join(seamless_dir, 
    "graphs", "bash_transformer.seamless"
)
zipfile = os.path.join(seamless_dir, 
    "graphs", "bash_transformer.zip"
)
graph = json.load(open(graphfile))
sctx = StaticContext.from_graph(graph)
sctx.add_zip(zipfile)

def translate_bash_transformer(node, root, namespace, inchannels, outchannels):
    from .translate import set_structured_cell_from_checksum
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

    with_result = node["with_result"]
    pins = node["pins"].copy()
    pins["bashcode"] = {"celltype": "text"}
    pins["pins_"] = {"celltype": "plain"}
    ctx.pins = cell("plain").set(list(pins.keys()))

    interchannels = [as_tuple(pin) for pin in pins]
    mount = node.get("mount", {})
    inp, inp_ctx = build_structured_cell(
      ctx, input_name, inchannels, interchannels,
      hash_pattern= node.get("hash_pattern"),
      return_context=True
    )
    setattr(ctx, input_name, inp)
    namespace[node["path"] + ("SCHEMA",), False] = inp.schema, node
    if "input_schema" in mount:
        inp_ctx.schema.mount(**mount["input_schema"])
    for inchannel in inchannels:
        path = node["path"] + inchannel
        namespace[path, True] = inp.inchannels[inchannel], node

    assert result_name not in pins #should have been checked by highlevel
    all_pins = {}
    for pinname, pin in pins.items():
        p = {"io": "input"}
        p.update(pin)
        all_pins[pinname] = p
    all_pins[result_name] = {"io": "output"}    
    if node["SCHEMA"]:
        assert with_result
        raise NotImplementedError
        all_pins[node["SCHEMA"]] = {
            "io": "input", "transfer_mode": "json",
            "access_mode": "json", "content_type": "json"
        }
    ctx.tf = transformer(all_pins)
    if node["debug"]:
        ctx.tf.debug = True
    ctx.code = cell("text")
    if "code" in mount:
        ctx.code.mount(**mount["code"])

    ctx.pins.connect(ctx.tf.pins_)
    ctx.code.connect(ctx.tf.bashcode)
    checksum = node.get("checksum", {})
    if "code" in checksum:
        ctx.code._set_checksum(checksum["code"], initial=True)
    inp_checksum = {}
    for k in checksum:
        if k == "schema":
            inp_checksum[k] = checksum[k]
            continue
        if not k.startswith("input"):
            continue
        k2 = "value" if k == "input" else k[len("input_"):]
        inp_checksum[k2] = checksum[k]
    set_structured_cell_from_checksum(inp, inp_checksum)

    ctx.executor_code = sctx.executor_code.cell()
    ctx.executor_code.connect(ctx.tf.code)

    namespace[node["path"] + ("code",), True] = ctx.code, node
    namespace[node["path"] + ("code",), False] = ctx.code, node

    for pinname, pin in node["pins"].items():
        target = getattr(ctx.tf, pinname)
        celltype = pin.get("celltype", "mixed")
        if celltype == "code":
            celltype = "text"        
        intermediate_cell = cell(celltype)
        setattr(ctx, pin_intermediate[pinname], intermediate_cell)
        inp.outchannels[(pinname,)].connect(intermediate_cell)
        intermediate_cell.connect(target)

    if with_result:
        result, result_ctx = build_structured_cell(
            ctx, result_name, [()],
            outchannels,
            return_context=True
        )
        namespace[node["path"] + ("RESULTSCHEMA",), False] = result.schema, node
        if "result_schema" in mount:
            result_ctx.schema.mount(**mount["result_schema"])

        setattr(ctx, result_name, result)

        result_pin = getattr(ctx.tf, result_name)        
        result_cell = cell("mixed")
        setattr(ctx, result_cell_name, result_cell)
        result_pin.connect(result_cell)
        result_cell.connect(result.inchannels[()])
        if node["SCHEMA"]:
            schema_pin = getattr(ctx.tf, node["SCHEMA"])
            result.schema.connect(schema_pin)
        result_checksum = {}        
        for k in checksum:
            if not k.startswith("result"):
                continue
            k2 = "value" if k == "result" else k[len("result_"):]
            result_checksum[k2] = checksum[k]
        set_structured_cell_from_checksum(result, result_checksum)
    else:
        for c in outchannels:
            assert len(c) == 0 #should have been checked by highlevel
        result = getattr(ctx.tf, result_name)
        namespace[node["path"] + (result_name,), False] = result, node

    namespace[node["path"], True] = inp, node
    namespace[node["path"], False] = result, node

from .util import get_path, as_tuple, build_structured_cell
