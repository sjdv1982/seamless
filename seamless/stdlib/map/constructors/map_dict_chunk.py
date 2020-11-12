def constructor(
  ctx, libctx,
  chunksize, context_graph, inp, keyorder0, result, elision, elision_chunksize, keyorder
):
    m = ctx.m = Macro()
    m.elision = elision
    m.graph = context_graph
    m.pins.graph.celltype = "plain"

    m.pins.result = {"io": "output", "celltype": "mixed", "hash_pattern": {"*": "#"}}

    m.chunksize = chunksize
    m.pins.chunksize.celltype = "int"

    m.elision_ = elision
    m.pins.elision_.celltype = "bool"
    m.elision_chunksize = elision_chunksize
    m.pins.elision_chunksize.celltype = "int"

    c = Cell()
    ctx.inp1 = c
    c.hash_pattern = {"*": "#"}
    inp.connect(c)
    ctx.inp2 = Cell("checksum")
    ctx.inp2 = ctx.inp1
    m.inp = ctx.inp2
    m.pins.inp.celltype = "plain"

    lib_module_dict = libctx.lib_module_dict.value
    ctx.lib_module_dict = Cell("plain").set(lib_module_dict)  # not strictly necessary to create a cell
    m.lib_module_dict = ctx.lib_module_dict
    m.pins.lib_module_dict.celltype = "plain"

    ctx.keyorder0 = Cell("plain").set(keyorder0)
    ctx.calc_keyorder = Transformer()
    ctx.calc_keyorder.code = lib_module_dict["helper"]["calc_keyorder"]
    ctx.calc_keyorder.inp_ = ctx.inp2
    ctx.calc_keyorder.pins.inp_.celltype = "plain"
    ctx.calc_keyorder.keyorder0 = ctx.keyorder0
    ctx.calc_keyorder.pins.keyorder0.celltype = "plain"
    ctx.keyorder = ctx.calc_keyorder
    ctx.keyorder.celltype = "plain"
    m.keyorder = ctx.keyorder
    keyorder.connect_from(ctx.keyorder)
    m.pins.keyorder.celltype = "plain"

    lib_codeblock = libctx.lib_codeblock.value
    ctx.lib_codeblock = Cell("plain").set(lib_codeblock)  # not strictly necessary to create a cell
    m.lib_codeblock = ctx.lib_codeblock
    m.pins.lib_codeblock.celltype = "plain"

    lib_code = {
        "type": "interpreted",
        "language": "python",
        "code": lib_codeblock
    }
    ctx.lib_code = Cell("plain").set(lib_code)  # not strictly necessary to create a cell
    m.lib = ctx.lib_code
    m.pins.lib.celltype = "plain"
    m.pins.lib.subcelltype = "module"

    if elision:
        m.code = lib_module_dict["map_dict_chunk"]["top"]
    else:
        m.code = lib_module_dict["map_dict_chunk"]["main"]
    ctx.result = Cell()
    ctx.result.hash_pattern = {"*": "#"}
    ctx.result = m.result
    result.connect_from(ctx.result)

constructor_params = {
    "context_graph": "context",
    "inp": {
        "type": "cell",
        "io": "input"
    },
    "chunksize": {
        "type": "value",
        "default": 10
    },
    "keyorder0": {
        "type": "value",
        "io": "input",
        "default": []
    },
    "result": {
        "type": "cell",
        "io": "output"
    },
    "keyorder": {
        "type": "cell",
        "celltype": "plain",
        "io": "output"
    },
    "elision": {
        "type": "value",
        "default": False
    },
    "elision_chunksize": {
        "type": "value",
        "default": 100
    },
}
