def constructor(
    ctx, libctx, context_graph, 
    inp, uniform,
    result, elision, elision_chunksize
):
    m = ctx.m = Macro()
    m.elision = elision
    m.graph = context_graph
    m.pins.graph.celltype = "plain"

    m.pins.result = {"io": "output", "celltype": "mixed", "hash_pattern": {"!": "#"}}

    m.elision_ = elision
    m.pins.elision_.celltype = "bool"
    m.elision_chunksize = elision_chunksize
    m.pins.elision_chunksize.celltype = "int"

    c = Cell()
    ctx.inp1 = c
    c.hash_pattern = {"!": "#"}
    inp.connect(c)
    ctx.inp2 = Cell("checksum")
    ctx.inp2 = ctx.inp1
    m.inp = ctx.inp2
    m.pins.inp.celltype = "checksum"

    if uniform is not None:
        c = ctx.uniform = Cell("mixed")
        uniform.connect(c)
        m.pins.uniform = {"io": "input", "celltype": "mixed"}
        m.uniform = c
        m.has_uniform = True
    else:
        m.has_uniform = False

    lib_module_dict = libctx.lib_module_dict.value
    ctx.lib_module_dict = Cell("plain").set(lib_module_dict)  # not strictly necessary to create a cell
    m.lib_module_dict = ctx.lib_module_dict
    m.pins.lib_module_dict.celltype = "plain"

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
    m.pins.lib.celltype = "module"

    if elision:
        m.code = lib_module_dict["map_list"]["top"]
    else:
        m.code = lib_module_dict["map_list"]["main"]
    ctx.result = Cell()
    ctx.result.hash_pattern = {"!": "#"}
    ctx.result = m.result
    result.connect_from(ctx.result)

constructor_params = {
    "context_graph": "context",
    "inp": {
        "type": "cell",
        "io": "input"
    },
    "uniform": {
        "type": "cell",
        "io": "input",
        "must_be_defined": False,
    },
    "result": {
        "type": "cell",
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
