from seamless.core import cell as core_cell, link as core_link, \
 libcell, transformer, reactor, context, macro, StructuredCell

from seamless.core import library

def translate_bash_transformer(node, root, namespace, inchannels, outchannels, lib_path00, is_lib):
    #TODO: simple translation, without a structured cell
    #TODO: there is a lot of common code with py transformer
    assert not "code" in node ### node["code"] is an outdated attribute

    # Just to register the "bash_transformer" lib
    from seamless.core.macro_mode import get_macro_mode, curr_macro    
    from seamless.lib.bash_transformer import bash_transformer as _

    inchannels = [ic for ic in inchannels if ic[0] != "code"]

    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    lib_path0 = lib_path00 + "." + name if lib_path00 is not None else None
    ctx = context(toplevel=False)
    setattr(parent, name, ctx)

    result_name = node["RESULT"]
    input_name = node["INPUT"]
    for c in inchannels:
        assert (not len(c)) or c[0] != result_name #should have been checked by highlevel

    with_result = node["with_result"]
    buffered = node["buffered"]
    pins = node["pins"].copy()
    for extrapin in ("bashcode", "pins"):
        assert extrapin not in node["pins"], extrapin
        pins[extrapin] =  {
            "transfer_mode": "ref",
            "access_mode": "plain",
            "content_type": None,
        }
    ctx.pins = core_cell("plain").set(list(pins.keys()))

    interchannels = [as_tuple(pin) for pin in pins]
    plain = node["plain"]
    mount = node.get("mount", {})
    inp, inp_ctx = build_structured_cell(
      ctx, input_name, True, plain, buffered, inchannels, interchannels,
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

    assert result_name not in pins #should have been checked by highlevel
    all_pins = {}
    for pinname, pin in pins.items():
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
        ctx.code = core_cell("text")
        if "code" in mount:
            ctx.code.mount(**mount["code"])
        ctx.code._sovereign = True

    ctx.pins.connect(ctx.tf.pins)
    ctx.code.connect(ctx.tf.bashcode)
    checksum = node.get("checksum", {})
    if "code" in checksum:
        ctx.code._set_checksum(checksum["code"], initial=True)
    if "schema" in checksum:
        inp._set_checksum(checksum["schema"], schema=True, initial=True)
    if "input" in checksum:
        inp._set_checksum(checksum["input"], initial=True)

    with library.bind("bash_transformer"):
        ctx.executor_code = libcell(".executor_code")    
    ctx.executor_code.connect(ctx.tf.code)

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
            result._set_checksum(checksum["result"], initial=True)
        if "result_schema" in checksum:
            result._set_checksum(checksum["result_schema"], schema=True, initial=True))
    else:
        for c in outchannels:
            assert len(c) == 0 #should have been checked by highlevel
        result = getattr(ctx.tf, result_name)
        namespace[node["path"] + (result_name,), False] = result, node

    namespace[node["path"], True] = inp, node
    namespace[node["path"], False] = result, node

from .util import get_path, as_tuple, build_structured_cell
