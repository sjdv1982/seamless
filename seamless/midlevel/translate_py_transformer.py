from seamless.core import cell as core_cell, link as core_link, \
 libcell, transformer, reactor, context, macro, StructuredCell

def translate_py_transformer(node, root, namespace, inchannels, outchannels, lib_path00, is_lib):
    #TODO: simple translation, without a structured cell    

    inchannels = [ic for ic in inchannels if ic[0] != "code"]

    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    lib_path0 = lib_path00 + "." + name if lib_path00 is not None else None
    ctx = context(toplevel=False)
    setattr(parent, name, ctx)

    result_name = node["RESULT"]
    if node["language"] == "ipython":
        assert result_name == "result"
    input_name = node["INPUT"]
    for c in inchannels:
        assert (not len(c)) or c[0] != result_name #should have been checked by highlevel

    with_result = node["with_result"]
    buffered = node["buffered"]
    interchannels = [as_tuple(pin) for pin in node["pins"]]
    plain = node["plain"]
    mount = node.get("mount", {})
    silk = (buffered or not plain)
    inp, inp_ctx = build_structured_cell(
      ctx, input_name, silk, plain, buffered, inchannels, interchannels,
      lib_path0,
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
    all_pins[result_name] = {"io": "output", "transfer_mode": "copy"}
    if node["SCHEMA"]:
        assert with_result
        all_pins[node["SCHEMA"]] = {
            "io": "input", "transfer_mode": "json",
            "access_mode": "json", "content_type": "json"
        }
    ctx.tf = transformer(all_pins)
    if node["debug"]:
        ctx.tf.debug = True
    if lib_path00 is not None:
        lib_path = lib_path00 + "." + name + ".code"
        ctx.code = libcell(lib_path)
    else:
        if node["language"] == "ipython":
            ctx.code = core_cell("ipython")
        else:
            ctx.code = core_cell("transformer")
        if "code" in mount:
            ctx.code.mount(**mount["code"])
        ctx.code._sovereign = True

    ctx.code.connect(ctx.tf.code)
    checksum = node.get("checksum", {})
    if "code" in checksum:
        ctx.code.set_checksum(checksum["code"])
    if "schema" in checksum:
        inp.set_schema_checksum(checksum["schema"])
    if "input" in checksum:
        inp.set_checksum(checksum["input"])
    namespace[node["path"] + ("code",), True] = ctx.code, node
    namespace[node["path"] + ("code",), False] = ctx.code, node

    for pin in list(node["pins"].keys()):
        target = getattr(ctx.tf, pin)
        inp.outchannels[(pin,)].connect(target)

    if with_result:
        plain_result = node["plain_result"]
        result, result_ctx = build_structured_cell(
            ctx, result_name, True, plain_result, False, [()],
            outchannels, lib_path0,
            return_context=True
        )
        namespace[node["path"] + ("RESULTSCHEMA",), False] = result.schema, node
        if "result_schema" in mount:
            result_ctx.schema.mount(**mount["result_schema"])

        setattr(ctx, result_name, result)

        result_pin = getattr(ctx.tf, result_name)
        result_pin.connect(result.inchannels[()])
        if node["SCHEMA"]:
            schema_pin = getattr(ctx.tf, node["SCHEMA"])
            result.schema.connect(schema_pin)
        if "result" in checksum:
            result.set_checksum(checksum["result"])
        if "result_schema" in checksum:
            result.set_schema_checksum(checksum["result_schema"])
    else:
        for c in outchannels:
            assert len(c) == 0 #should have been checked by highlevel
        result = getattr(ctx.tf, result_name)
        namespace[node["path"] + (result_name,), False] = result, node

    namespace[node["path"], True] = inp, node
    namespace[node["path"], False] = result, node

from .util import get_path, as_tuple, build_structured_cell
