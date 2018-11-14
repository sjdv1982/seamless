from seamless.core import cell, libcell, transformer, context, StructuredCell

from seamless.core import StructuredCell
from seamless.core import library


def _init_from_library(ctf):
    # Just to register the "compiled_transformer" lib
    from seamless.lib.compiled_transformer import compiled_transformer as _
    with library.bind("compiled_transformer"):
        ctf.gen_header_code = libcell(".gen_header.code")
        ctf.gen_header_params = libcell(".gen_header_params")
        ctf.gen_header = transformer(ctf.gen_header_params.value)
        ctf.gen_header_code.connect(ctf.gen_header.code)

        ctf.compiler_code = libcell(".compiler.code")
        ctf.compiler_params = libcell(".compiler_params")
        ctf.compiler = transformer(ctf.compiler_params.value)
        ctf.compiler_code.connect(ctf.compiler.code)

        ctf.translator_code = libcell(".translator.code")
        ctf.translator_params = libcell(".translator_params")
        ctf.translator = transformer(ctf.translator_params.value)
        ctf.translator_code.connect(ctf.translator.code)

def _finalize(ctx, ctf, inp, c_inp, result, c_result, input_name, result_name):
    #1: between transformer and library
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
    ctx.header.connect(ctf.compiler.header)

    ctx.language.connect(ctf.compiler.lang)
    ctx.code.connect(ctf.compiler.compiled_code)
    # TODO: interactive binary objects (structured cell)
    ctx.main_module.connect(ctf.compiler.main_module)
    ctx.compiler_verbose.connect(ctf.compiler.compiler_verbose)

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
    ctf.compiler.result.connect(ctx.binary_module)

    ctx.binary_module.connect(ctf.translator.binary_module)


def translate_compiled_transformer(node, root, namespace, inchannels, outchannels, lib_path00, is_lib):
    #TODO: still a lot of common code with translate_py_transformer, put in functions
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

    plain = node["plain"]
    input_state = node.get("stored_state_input", None)
    mount = node.get("mount", {})
    if input_state is None:
        input_state = node.get("cached_state_input", None)
    inp, inp_ctx = build_structured_cell(
      ctx, input_name, True, plain, buffered, inchannels, [()],
      input_state, lib_path0,
      return_context=True
    )
    setattr(ctx, input_name, inp)
    if "input_schema" in mount:
        inp_ctx.schema.mount(**mount["input_schema"])
    for inchannel in inchannels:
        path = node["path"] + inchannel
        namespace[path, True] = inp.inchannels[inchannel], node

    assert result_name not in node["pins"] #should have been checked by highlevel
    assert "translator_result_" not in node["pins"] #should have been checked by highlevel
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

    ctf = ctx.tf = context(name="tf",context=ctx)
    _init_from_library(ctf)

    if lib_path00 is not None:
        lib_path = lib_path00 + "." + name + ".code"
        ctx.code = libcell(lib_path)
    else:
        ctx.code = cell("text")
        ctx.code.set_file_extension(node["file_extension"])
        if "code" in mount:
            ctx.code.mount(**mount["code"])

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
    assert not node["SCHEMA"]

    ctx.language = cell("text").set(node["language"])
    ctx.main_module = cell("json").set(node["main_module"])
    compiler_verbose = node["main_module"]["compiler_verbose"]
    ctx.compiler_verbose = cell("json").set(True)
    ctx.pins = cell("json").set(all_pins)
    c_inp = getattr(ctx, input_name + STRUC_ID)
    c_result = getattr(ctx, result_name + STRUC_ID)
    _finalize(ctx, ctf, inp, c_inp, result, c_result, input_name, result_name)

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
    namespace[node["path"] + ("code",), True] = ctx.code, node
    namespace[node["path"] + ("code",), False] = ctx.code, node

    if not is_lib: #clean up cached state and in_equilibrium, unless a library context
        node.pop("cached_state_input", None)
        if not in_equilibrium:
            node.pop("cached_state_result", None)
        node.pop("in_equilibrium", None)

    namespace[node["path"], True] = inp, node
    namespace[node["path"], False] = result, node
    node.pop("TEMP", None)

from .util import get_path, as_tuple, build_structured_cell, STRUC_ID
