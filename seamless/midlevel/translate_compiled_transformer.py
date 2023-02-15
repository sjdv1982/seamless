import os, json
from seamless.core import cell, transformer, context
from ..metalevel.stdgraph import load as load_stdgraph

def _init_from_graph(ctf, sctx):
    ctf.gen_header_code = sctx.gen_header.code.cell()
    ctf.gen_header_params = sctx.gen_header_params.cell()
    ctf.gen_header = transformer(sctx.gen_header_params.value)
    ctf.gen_header_code.connect(ctf.gen_header.code)

    ctf.integrator_code = sctx.integrator.code.cell()
    ctf.integrator_params = sctx.integrator_params.cell()
    ctf.integrator = transformer(sctx.integrator_params.value)    
    ctf.integrator_code.connect(ctf.integrator.code)

    ctf.executor_code = sctx.executor.code.cell()
    ctf.executor_params = sctx.executor_params.cell()
    ctf.executor = transformer(sctx.executor_params.value)
    ctf.executor_code.connect(ctf.executor.code)

    ctf.executor.DIRECT_PRINT.cell().set(False)

def _finalize(
        ctx, ctf, inp, c_inp, result, c_result,
        input_name, result_name, inchannels, node):
    result_cell_name1 = result_name + "_CELL1"
    result_cell_name2 = result_name + "_CELL2"
    input_cell_name = input_name + "_CELL"
    link_options_cell_name = "LINK_OPTIONS_CELL"
    main_module_cell_name = input_name + "_MAIN_MODULE_CELL"
    forbidden = (
        result_name, result_cell_name1,
        result_cell_name2, input_cell_name,
        link_options_cell_name,
        main_module_cell_name
    )
    for c in inchannels:
        assert (not len(c)) or c[0] not in forbidden #should have been checked by highlevel

    result_cell1 = cell("mixed")
    cell_setattr(node, ctx, result_cell_name1, result_cell1)
    result_cell2 = cell("mixed")
    cell_setattr(node, ctx, result_cell_name2, result_cell2)
    input_cell = cell("mixed")
    cell_setattr(node, ctx, input_cell_name, input_cell)
    link_options_cell = cell("plain")
    cell_setattr(node, ctx, link_options_cell_name, link_options_cell)
    main_module_cell = cell("plain")
    cell_setattr(node, ctx, main_module_cell_name, main_module_cell)

    link_options_cell.connect(
        ctx.main_module.inchannels[("link_options",)]
    )
    link_options_cell.set(node.get("link_options", []))
    #1: between transformer and library

    ctx.inputpins.connect(ctf.gen_header.inputpins)
    ctx.pins.connect(ctf.executor.pins)
    ctf.executor.result.connect(result_cell1)
    result_cell1.connect(result.inchannels[()])
    inp.outchannels[()].connect(input_cell)
    input_cell.connect(ctf.executor.kwargs)
    c_inp.schema.connect(ctf.gen_header.input_schema)
    c_result.schema.connect(ctf.gen_header.result_schema)
    c_inp.schema.connect(ctf.executor.input_schema)
    c_result.schema.connect(ctf.executor.result_schema)

    ctf.gen_header.input_name.cell().set(input_name)
    ctf.gen_header.result_name.cell().set(result_name)
    ctf.executor.input_name.cell().set(input_name)
    ctf.executor.result_name.cell().set(result_name)

    #2: among library cells
    ctx.header = cell("text")
    ctf.gen_header.result.connect(ctx.header)
    ctx.header.connect(ctf.integrator.header_)

    ctx.language.connect(ctf.integrator.lang)
    ctx.code.connect(ctf.integrator.compiled_code)
    ctx.main_module.outchannels[()].connect(main_module_cell)
    main_module_cell.connect(ctf.integrator.main_module)

    ctx.module = cell("mixed")
    ctf.integrator.result.connect(ctx.module)

    ctx.module.connect(ctf.executor.module)

def translate_compiled_transformer(
        node, root, namespace, inchannels, outchannels,
        *, has_meta_connection
    ):
    from .translate import set_structured_cell_from_checksum
    from ..highlevel.Environment import Environment
    
    env0 = Environment(None)
    env0._load(node.get("environment"))
    env = env0._to_lowlevel()

    for pinname,pin in list(node["pins"].items()):
        if pin.get("celltype", "default") != "default":
            raise ValueError("Compiled transformer celltype must be 'default', not celltype '{}' (pin '{}')".format(pin["celltype"], pin))
    if node.get("result_celltype", "structured") != "structured":
        raise ValueError("Compiled transformer result celltype must be 'structured', not celltype '{}'".format(node["result_celltype"]))
    inchannels = [ic for ic in inchannels if ic[0] != "code"]

    main_module_inchannels = [("link_options",), ("headers",)]
    for ic in inchannels:
        if ic[0] != "_main_module":
            continue
        if ic[1:] == ("headers",):
            continue
        else:
            main_module_inchannels.append(("objects",) + ic[1:])
    inchannels = [ic for ic in inchannels if ic[0] != "_main_module"]

    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    ctx = context(toplevel=False)
    setattr(parent, name, ctx)

    result_name = node["RESULT"]
    input_name = node["INPUT"]
    
    inputpins = []
    all_inchannels = set(inchannels)
    pin_cells = {}
    for pin in list(node["pins"].keys()):
        pin_cell_name = pin + "_PIN"
        assert pin_cell_name not in all_inchannels
        assert pin_cell_name not in node["pins"]
        pin_cell = cell("mixed")
        cell_setattr(node, ctx, pin_cell_name, pin_cell)
        pin_cells[pin] = pin_cell

    mount = node.get("mount", {})
    inp, inp_ctx = build_structured_cell(
      ctx, input_name, inchannels, [()],
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

    assert result_name not in node["pins"] #should have been checked by highlevel
    assert "executor_result_" not in node["pins"] #should have been checked by highlevel
    all_pins = {}
    inputpins = []
    for pinname, pin in node["pins"].items():
        p = {"io": "input"}
        p.update(pin)
        all_pins[pinname] = p
        inputpins.append(pinname)
    all_pins[result_name] = {"io": "output"}
    if node["SCHEMA"]:
        all_pins[node["SCHEMA"]] = {
            "io": "input", "celltype": "mixed"
        }

    # Compiler
    ctx.language = cell("str").set(node["language"])

    ctx.main_module = build_structured_cell(
      ctx, "main_module",
      main_module_inchannels, [()],
      fingertip_no_remote=node.get("fingertip_no_remote", False),
      fingertip_no_recompute=node.get("fingertip_no_recompute", False),
    )

    for ic in main_module_inchannels:
        if len(ic) == 1 and ic[-1] in ("link_options", "headers"):
            continue
        icpath = node["path"] + ("_main_module",) + ic[1:]
        namespace[icpath, "target"] = ctx.main_module.inchannels[ic], node

    # Transformer itself
    ctf = ctx.tf = context()
    sctx = load_stdgraph("compiled_transformer")
    _init_from_graph(ctf, sctx)
    ctf.integrator.debug_.cell().set(False)

    if has_meta_connection:
        ctx.meta = cell("plain")
        ctx.meta.connect(ctf.executor.META)
        namespace[node["path"] + ("meta",), "target"] = ctx.meta, node
    else:
        meta = node.get("meta")
        if meta is not None:
            ctf.executor.meta = meta

    ctx.code = cell("text")
    ctx.code.set_file_extension(node["file_extension"])
    if "code" in mount:
        ctx.code.mount(**mount["code"])

    checksum = node.get("checksum", {})
    if "code" in checksum:
        ctx.code._set_checksum(checksum["code"], initial=True)
    main_module_checksum = checksum.get("main_module",
      'd0a1b2af1705c1b8495b00145082ef7470384e62ac1c4d9b9cdbbe0476c28f8c' # {}
    )
    set_structured_cell_from_checksum(ctx.main_module, {"auth": main_module_checksum})
    inp_checksum = convert_checksum_dict(checksum, "input")
    set_structured_cell_from_checksum(inp, inp_checksum)
    namespace[node["path"] + ("code",), "target"] = ctx.code, node
    namespace[node["path"] + ("code",), "source"] = ctx.code, node

    # main module headers
    headers_cell = cell("plain")
    setattr(ctx, "main_module_headers_CELL", headers_cell)
    headers_cell.connect(
        ctx.main_module.inchannels[("headers",)]
    )
    namespace[node["path"] + ("_main_module", "headers"), "target"] = headers_cell, node        

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
    assert not node["SCHEMA"]

    result_checksum = {}
    for k in checksum:
        if not k.startswith("result"):
            continue
        k2 = "value" if k == "result" else k[len("result_"):]
        result_checksum[k2] = checksum[k]
    set_structured_cell_from_checksum(result, result_checksum)

    ctx.pins = cell("plain").set(all_pins)
    ctx.inputpins = cell("plain").set(inputpins)
    c_inp = getattr(ctx, input_name + STRUC_ID)
    c_result = getattr(ctx, result_name + STRUC_ID)
    _finalize(
        ctx, ctf, inp, c_inp, result, c_result,
        input_name, result_name,
        inchannels, node
    )

    if "header" in mount:
        ctx.header.mount(**mount["header"])
    namespace[node["path"] + ("header",), "source"] = ctx.header, node

    if env is not None:
        ctf.executor.env = env

    namespace[node["path"], "target"] = inp, node
    namespace[node["path"], "source"] = result, node

from .util import get_path, build_structured_cell, cell_setattr, STRUC_ID
from .convert_checksum_dict import convert_checksum_dict