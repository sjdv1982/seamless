def constructor(ctx, libctx, context_graph, inp, result, elision, elision_chunksize):
    m = ctx.m = Macro()
    m.elision = elision
    m.graph = context_graph
    m.pins.graph.celltype = "plain"

    m.pins.result = {"io": "output", "celltype": "mixed", "hash_pattern": {"!": "#"}}

    ctx.inp1 = Context()
    ctx.inp2 = Context()
    ctx.inp3 = Cell()

    m.elision_ = elision
    m.pins.elision_.celltype = "bool"
    m.elision_chunksize = elision_chunksize
    m.pins.elision_chunksize.celltype = "int"

    for var in inp:
        c = Cell()
        ctx.inp1[var] = c
        c.hash_pattern = {"!": "#"}
        inp[var].connect(c)
        ctx.inp2[var] = Cell("checksum")
        ctx.inp2[var] = ctx.inp1[var]
        ctx.inp3[var] = ctx.inp2[var]
    m.inp = ctx.inp3
    m.pins.inp.celltype = "plain"

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
    m.pins.lib.celltype = "plain"
    m.pins.lib.subcelltype = "module"

    if elision:
        m.code = lib_module_dict["map_list_N"]["top"]
    else:
        m.code = lib_module_dict["map_list_N"]["main"]
    ctx.result = Cell()
    ctx.result.hash_pattern = {"!": "#"}
    ctx.result = m.result
    result.connect_from(ctx.result)

constructor_params = {
    "context_graph": "context",
    "inp": {
        "type": "celldict",  # TODO: enforce hash pattern
        "io": "input"
    },
    "result": {
        "type": "cell",
        "io": "output"
    },
    "elision": {
        "type": "value",
        "default": False   # TODO: implement default
    },
    "elision_chunksize": {
        "type": "value",
        "default": 100  # TODO: implement default
    },
}
