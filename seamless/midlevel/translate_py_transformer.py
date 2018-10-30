from seamless.core import cell as core_cell, link as core_link, \
 libcell, libmixedcell, transformer, reactor, context, macro, StructuredCell

def translate_py_transformer(node, root, namespace, inchannels, outchannels, lib_path00, is_lib):
    #TODO: simple translation, without a structured cell
    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    lib_path0 = lib_path00 + "." + name if lib_path00 is not None else None
    ctx = context(context=parent, name=name)
    setattr(parent, name, ctx)

    result_name = node["RESULT"]
    input_name = node["INPUT"]
    if len(inchannels):
        lib_path0 = None #partial authority or no authority; no library update in either case
    for c in inchannels:
        assert (not len(c)) or c[0] != result_name #should have been checked by highlevel

    with_result = node["with_result"]
    buffered = node["buffered"]
    interchannels = [as_tuple(pin) for pin in node["pins"]]
    plain = node["plain"]
    input_state = node.get("stored_state_input", None)
    mount = node.get("mount", {})
    if input_state is None:
        input_state = node.get("cached_state_input", None)
    inp, inp_ctx = build_structured_cell(
      ctx, input_name, True, plain, buffered, inchannels, interchannels,
      input_state, lib_path0,
      return_context=True
     )
    setattr(ctx, input_name, inp)
    if "schema" in mount:
        inp_ctx.schema.mount(**mount["schema"])
    for inchannel in inchannels:
        path = node["path"] + inchannel
        namespace[path, True] = inp.inchannels[inchannel]

    assert result_name not in node["pins"] #should have been checked by highlevel
    all_pins = {}
    for pinname, pin in node["pins"].items():
        p = {"io": "input"}
        p.update(pin)
        all_pins[pinname] = p
    all_pins[result_name] = "output"
    if node["SCHEMA"]:
        assert with_result
        all_pins[node["SCHEMA"]] = {
            "io": "input", "transfer_mode": "json",
            "access_mode": "json", "content_type": "json"
        }
    in_equilibrium = node.get("in_equilibrium", False)
    ctx.tf = transformer(all_pins, in_equilibrium=in_equilibrium)
    if lib_path00 is not None:
        lib_path = lib_path00 + "." + name + ".code"
        ctx.code = libcell(lib_path)
    else:
        ctx.code = core_cell("transformer")
        if "code" in mount:
            ctx.code.mount(**mount["code"])

    ctx.code.connect(ctx.tf.code)
    code = node.get("code")
    if code is None:
        code = node.get("cached_code")
    ctx.code.set(code)
    temp = node.get("TEMP")
    if temp is None:
        temp = {}
    if "code" in temp:
        ctx.code.set(temp["code"])
    inphandle = inp.handle
    for k,v in temp.items():
        if k == "code":
            continue
        setattr(inphandle, k, v)
    namespace[node["path"] + ("code",), True] = ctx.code
    namespace[node["path"] + ("code",), False] = ctx.code

    for pin in list(node["pins"].keys()):
        target = getattr(ctx.tf, pin)
        inp.connect_outchannel( (pin,) ,  target )

    if with_result:
        plain_result = node["plain_result"]
        result_state = node.get("cached_state_result", None)
        result, result_ctx = build_structured_cell(
            ctx, result_name, True, plain_result, False, [()],
            outchannels, result_state, lib_path0,
            return_context=True
        )
        if "result_schema" in mount:
            result_ctx.schema.mount(**mount["result_schema"])

        setattr(ctx, result_name, result)

        result_pin = getattr(ctx.tf, result_name)
        result.connect_inchannel(result_pin, ())
        if node["SCHEMA"]:
            schema_pin = getattr(ctx.tf, node["SCHEMA"])
            result.schema.connect(schema_pin)
    else:
        for c in outchannels:
            assert len(c) == 0 #should have been checked by highlevel
        result = getattr(ctx.tf, result_name)
        namespace[node["path"] + (result_name,), False] = result

    if not is_lib: #clean up cached state and in_equilibrium, unless a library context
        node.pop("cached_state_input", None)
        if not in_equilibrium:
            node.pop("cached_state_result", None)
        node.pop("in_equilibrium", None)

    namespace[node["path"], True] = inp
    namespace[node["path"], False] = result
    node.pop("TEMP", None)

from .util import get_path, as_tuple, build_structured_cell
