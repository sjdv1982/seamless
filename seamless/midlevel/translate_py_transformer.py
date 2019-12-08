from seamless.core import cell, link, \
 transformer, context, StructuredCell

def translate_py_transformer(node, root, namespace, inchannels, outchannels):
    from .translate import set_structured_cell_from_checksum
    #TODO: simple translation, without a structured cell    

    inchannels = [ic for ic in inchannels if ic[0] != "code"]

    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    ctx = context(toplevel=False)
    setattr(parent, name, ctx)

    result_name = node["RESULT"]
    result_cell_name = result_name + "_CELL"
    if node["language"] == "ipython":
        assert result_name == "result"
    input_name = node["INPUT"]
    for c in inchannels:
        assert (not len(c)) or c[0] not in (result_name, result_cell_name) #should have been checked by highlevel
    all_inchannels = set(inchannels)
    pin_cells = {}
    for pin in list(node["pins"].keys()):
        pin_cell_name = pin + "_INCHANNEL"
        assert pin_cell_name not in all_inchannels
        assert pin_cell_name not in node["pins"]
        pin_cell = cell("mixed")
        setattr(ctx, pin_cell_name, pin_cell)
        pin_cells[pin] = pin_cell
        

    with_result = node["with_result"]
    interchannels = [as_tuple(pin) for pin in node["pins"]]
    mount = node.get("mount", {})    
    inp, inp_ctx = build_structured_cell(
      ctx, input_name, inchannels, interchannels,
      return_context=True
    )

    setattr(ctx, input_name, inp)
    namespace[node["path"] + ("SCHEMA",), False] = inp.schema, node    
    if "input_schema" in mount:
        inp_ctx.schema.mount(**mount["input_schema"])
    for inchannel in inchannels:
        path = node["path"] + inchannel
        namespace[path, True] = inp.inchannels[inchannel], node

    assert result_name not in node["pins"] #should have been checked by highlevel
    all_pins = {}
    for pinname, pin in node["pins"].items():
        p = {"io": "input"}
        p.update(pin)
        all_pins[pinname] = p
    all_pins[result_name] = {"io": "output", "celltype": "mixed"}
    if node["SCHEMA"]:
        assert with_result
        all_pins[node["SCHEMA"]] = {
            "io": "input", "celltype": "mixed"
        }
    ctx.tf = transformer(all_pins)
    if node["debug"]:
        ctx.tf.debug = True
    if node["language"] == "ipython":
        ctx.code = cell("ipython")
    else:
        ctx.code = cell("transformer")
    if "code" in mount:
        ctx.code.mount(**mount["code"])

    ctx.code.connect(ctx.tf.code)
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
    namespace[node["path"] + ("code",), True] = ctx.code, node
    namespace[node["path"] + ("code",), False] = ctx.code, node

    for pin in list(node["pins"].keys()):
        target = getattr(ctx.tf, pin)
        pin_cell = pin_cells[pin]
        inp.outchannels[(pin,)].connect(pin_cell)
        pin_cell.connect(target)

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
