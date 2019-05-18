from seamless.core import cell, libcell, transformer, context, StructuredCell

from seamless.core import StructuredCell
from seamless.core import library


def _init_from_library(ctf, debug):
    # Just to register the "compiled_transformer" lib
    from seamless.lib.compiled_transformer import compiled_transformer as _
    with library.bind("compiled_transformer"):
        ctf.gen_header_code = libcell(".gen_header.code")
        ctf.gen_header_params = libcell(".gen_header_params")
        ctf.gen_header = transformer(ctf.gen_header_params.value)
        ctf.gen_header_code.connect(ctf.gen_header.code)

        ctf.integrator_code = libcell(".integrator.code")
        ctf.integrator_params = libcell(".integrator_params")
        ctf.integrator = transformer(ctf.integrator_params.value)
        ctf.integrator_code.connect(ctf.integrator.code)

        ctf.translator_code = libcell(".translator.code")
        ctf.translator_params = libcell(".translator_params")
        ctf.translator = transformer(ctf.translator_params.value)
        if debug:
            ctf.translator.debug = True
        ctf.translator_code.connect(ctf.translator.code)

def _finalize(ctx, ctf, inp, c_inp, result, c_result, input_name, result_name):
    #1: between transformer and library
    ctx.inputpins.connect(ctf.gen_header.inputpins)
    ctx.pins.connect(ctf.translator.pins)
    ctx.result.connect_inchannel(ctf.translator.translator_result_, ())
    inp.connect_outchannel((), ctf.translator.kwargs)
    c_inp.schema.connect(ctf.gen_header.input_schema)
    c_result.schema.connect(ctf.gen_header.result_schema)
    c_inp.schema.connect(ctf.translator.input_schema)
    c_result.schema.connect(ctf.translator.result_schema)

    ctf.gen_header.input_name.cell().set(input_name)
    ctf.gen_header.result_name.cell().set(result_name)
    ctf.translator.input_name.cell().set(input_name)
    ctf.translator.result_name.cell().set(result_name)

    #2: among library cells
    ctx.header = cell("text")
    ctf.gen_header.result.connect(ctx.header)
    ctx.header.connect(ctf.integrator.header)

    ctx.language.connect(ctf.integrator.lang)
    ctx.code.connect(ctf.integrator.compiled_code)
    ctx.main_module.connect_outchannel((), ctf.integrator.main_module)
    ctx.compiler_verbose.connect(ctf.integrator.compiler_verbose)

    ctx.binary_module_storage = cell("text")
    ctx.binary_module_storage._sovereign = True
    ctx.binary_module_form = cell("json")
    ctx.binary_module_form._sovereign = True
    ctx.binary_module = cell(
        "mixed",
        storage_cell = ctx.binary_module_storage,
        form_cell = ctx.binary_module_form,
    )
    ctx.binary_module._sovereign = True
    ctf.integrator.result.connect(ctx.binary_module)

    ctx.binary_module.connect(ctf.translator.binary_module)


def translate_compiled_transformer(node, root, namespace, inchannels, outchannels, lib_path00, is_lib):
    raise NotImplementedError ### cache branch
    #TODO: still a lot of common code with translate_py_transformer, put in functions
    from seamless.lib.compiled_transformer import compiled_transformer as _
    inchannels = [ic for ic in inchannels if ic[0] != "code"]

    main_module_inchannels = [("objects",) + ic[1:] for ic in inchannels if ic[0] == "_main_module"]
    inchannels = [ic for ic in inchannels if ic[0] != "_main_module"]

    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    lib_path0 = lib_path00 + "." + name if lib_path00 is not None else None
    ctx = context(context=parent, name=name)
    setattr(parent, name, ctx)

    input_name = node["INPUT"]
    result_name = node["RESULT"]
    if len(inchannels):
        lib_path0 = None #partial authority or no authority; no library update in either case
    for c in inchannels:
        assert (not len(c)) or c[0] != result_name #should have been checked by highlevel

    with_result = node["with_result"]
    assert with_result #compiled transformers must have with_result
    buffered = node["buffered"]

    mount = node.get("mount", {})
    plain = node["plain"]
    inp, inp_ctx = build_structured_cell(
      ctx, input_name, True, plain, buffered, inchannels, [()],
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
    assert "translator_result_" not in node["pins"] #should have been checked by highlevel
    all_pins = {}
    inputpins = []
    for pinname, pin in node["pins"].items():
        p = {"io": "input"}
        p.update(pin)
        if p["io"] == "input":
            inputpins.append(pinname)
        all_pins[pinname] = p
    all_pins[result_name] = "output"
    if node["SCHEMA"]:
        assert with_result
        all_pins[node["SCHEMA"]] = {
            "io": "input", "transfer_mode": "json",
            "access_mode": "json", "content_type": "json"
        }
    in_equilibrium = node.get("in_equilibrium", False)

    temp = node.get("TEMP")
    if temp is None:
        temp = {}

    # Compiler
    ctx.language = cell("text").set(node["language"])

    ctx.main_module = build_structured_cell(
      ctx, "main_module", False, True, False,
      main_module_inchannels, [()],
      lib_path00,
    )

    if "_main_module" in temp and len(temp["_main_module"]):
        temp_main_module = temp["_main_module"]
        main_module_handle = ctx.main_module.handle
        main_module_data = ctx.main_module.data.value
        if main_module_data is None:
            ctx.main_module.monitor.set_path((), {"objects":{}}, forced=True)
            main_module_data = ctx.main_module.data.value
        elif "objects" not in main_module_data:
            main_module_handle["objects"] = {}
        for objname, obj in temp_main_module.items():
            for key, value in obj.items():
                if objname in main_module_data["objects"] and \
                 key in main_module_data["objects"][objname]:
                    msg = "WARNING: %s main module object '%s': %s already defined"
                    print(msg % (node["path"], objname, key))
                    continue
                if objname not in main_module_data["objects"]:
                    ctx.main_module.monitor.set_path(
                      ("objects", objname), {}, forced=True
                    )
                main_module_handle["objects"][objname][key] = value

    for ic in main_module_inchannels:
        icpath = node["path"] + ("_main_module",) + ic[1:]
        namespace[icpath, True] = ctx.main_module.inchannels[ic], node

    compiler_verbose = node["main_module"]["compiler_verbose"]
    ctx.compiler_verbose = cell("json").set(compiler_verbose)

    target = node["main_module"].get("target")
    if target is not None:
        ctx.main_module.monitor.set_path(("target",), target, forced=True)

    # Transformer itself
    ctf = ctx.tf = context(name="tf",context=ctx)
    debug = node["debug"]
    _init_from_library(ctf, debug)

    if lib_path00 is not None:
        lib_path = lib_path00 + "." + name + ".code"
        ctx.code = libcell(lib_path)
    else:
        ctx.code = cell("text")
        ctx.code.set_file_extension(node["file_extension"])
        if "code" in mount:
            ctx.code.mount(**mount["code"])

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
    assert not node["SCHEMA"]

    ctx.pins = cell("json").set(all_pins)
    ctx.inputpins = cell("json").set(inputpins)
    c_inp = getattr(ctx, input_name + STRUC_ID)
    c_result = getattr(ctx, result_name + STRUC_ID)
    _finalize(ctx, ctf, inp, c_inp, result, c_result, input_name, result_name)

    if "header" in mount:
        ctx.header.mount(**mount["header"])

    if code is not None:
        ctx.code.set(code)
    if "code" in temp:
        ctx.code.set(temp["code"])
    inphandle = inp.handle
    for k,v in temp.items():
        if k in ("code", "_main_module"):
            continue
        setattr(inphandle, k, v)
    namespace[node["path"] + ("code",), True] = ctx.code, node
    namespace[node["path"] + ("code",), False] = ctx.code, node

    namespace[node["path"], True] = inp, node
    namespace[node["path"], False] = result, node
    node.pop("TEMP", None)

from .util import get_path, as_tuple, build_structured_cell, STRUC_ID
