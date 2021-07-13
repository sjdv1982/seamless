"""
Version of high-in-low6 with nested invocation and elision
"""

from seamless.highlevel import Context, Cell, Macro
from seamless.highlevel.library import LibraryContainer

def map_list_N(ctx, inp_prefix, graph, inp):
    print("map_list_N", inp)
    from seamless.core import Cell as CoreCell
    from seamless.core import cell
    from seamless.core.structured_cell import StructuredCell
    from seamless.core.HighLevelContext import HighLevelContext
    from seamless.core.unbound_context import UnboundContext

    first_k = list(inp.keys())[0]
    length = len(inp[first_k])
    first_k = first_k[len(inp_prefix):]
    for k0 in inp:
        k = k0[len(inp_prefix):]
        if len(inp[k0]) != length:
            err = "all cells in inp must have the same length, but '{}' has length {} while '{}' has length {}"
            raise ValueError(err.format(k, len(inp[k0]), first_k, length))

    pseudo_connections = []
    ctx.result = cell("mixed", hash_pattern = {"!": "#"})

    ctx.sc_data = cell("mixed", hash_pattern = {"!": "#"})
    ctx.sc_buffer = cell("mixed", hash_pattern = {"!": "#"})
    ctx.sc = StructuredCell(
        data=ctx.sc_data,
        buffer=ctx.sc_buffer,
        inchannels=[(n,) for n in range(length)],
        outchannels=[()],
        hash_pattern = {"!": "#"}
    )

    for n in range(length):
        hc = HighLevelContext(graph)

        subctx = "subctx%d" % (n+1)
        setattr(ctx, subctx, hc)

        if not hasattr(hc, "inp"):
            raise TypeError("map_list_N context must have a subcontext called 'inp'")
        hci = hc.inp
        if not isinstance(hci, UnboundContext):
            raise TypeError("map_list_N context must have an attribute 'inp' that is a context, not a {}".format(type(hci)))

        for k0 in inp:
            k = k0[len(inp_prefix):]
            if not hasattr(hci, k):
                raise TypeError("map_list_N context must have a cell called inp.'{}'".format(k))
            if isinstance(hci[k], StructuredCell):
                raise TypeError("map_list_N context has a cell called inp.'{}', but its celltype must be mixed, not structured".format(k))
            if not isinstance(hci[k], CoreCell):
                raise TypeError("map_list_N context must have an attribute inp.'{}' that is a cell, not a {}".format(k, type(hci[k])))
            if hci[k].celltype != "mixed":
                raise TypeError("map_list_N context has a cell called inp.'{}', but its celltype must be mixed, not {}".format(k, hci[k].celltype))

            con = [".." + k], ["ctx", subctx, "inp", k]
            pseudo_connections.append(con)
            cs = inp[k0][n]
            hci[k].set_checksum(cs)

        resultname = "result%d" % (n+1)
        setattr(ctx, resultname, cell("int"))
        c = getattr(ctx, resultname)
        hc.result.connect(c)
        c.connect(ctx.sc.inchannels[(n,)])
        con = ["ctx", subctx, "result"], ["..result"]
        pseudo_connections.append(con)

    ctx.sc.outchannels[()].connect(ctx.result)
    ctx._pseudo_connections = pseudo_connections

def map_list_N_nested(
  ctx, elision_chunksize, inp_prefix, graph, inp,
  *, map_list_N_nested_code, macro_code_lib_code,
  macro_code_lib0=None
):
    global macro_code_lib
    if macro_code_lib0 is not None:
        macro_code_lib = macro_code_lib0
    from seamless.core import cell, macro, context, path, transformer
    first_k = list(inp.keys())[0]
    length = len(inp[first_k])
    print("NEST", length, inp[first_k][0])
    first_k = first_k[len(inp_prefix):]
    for k0 in inp:
        k = k0[len(inp_prefix):]
        if len(inp[k0]) != length:
            err = "all cells in inp must have the same length, but '{}' has length {} while '{}' has length {}"
            raise ValueError(err.format(k, len(inp[k0]), first_k, length))

    if length > elision_chunksize:
        merge_subresults = """def merge_subresults(**subresults):
            result = []
            for k in sorted(subresults.keys()):
                v = subresults[k]
                result += v
            return result"""
        ctx.macro_code = cell("python").set(map_list_N_nested_code)
        ctx.macro_code_lib_code = cell("plain").set(macro_code_lib_code)
        ctx.macro_code_lib = cell("plain").set({
            "type": "interpreted",
            "language": "python",
            "code": macro_code_lib_code
        })
        ctx.graph = cell("plain").set(graph)
        ctx.inp_prefix = cell("str").set(inp_prefix)
        ctx.elision_chunksize = cell("int").set(elision_chunksize)
        chunk_index = 0

        macro_params = {
            'inp_prefix': {'celltype': 'str'},
            'elision_chunksize': {'celltype': 'int'},
            'graph': {'celltype': 'plain'},
            'inp': {'celltype': 'plain'},
            "map_list_N_nested_code": {'celltype': 'python'},
            "macro_code_lib": {'celltype': 'plain', 'subcelltype': 'module'},
            "macro_code_lib_code": {'celltype': 'plain'},
        }

        subresults = {}
        chunksize = elision_chunksize
        while chunksize * elision_chunksize < length:
            chunksize *= elision_chunksize
        for n in range(0, length, chunksize):
            chunk_inp = {}
            for k in inp:
                chunk_inp[k] = inp[k][n:n+chunksize]
            chunk_index += 1
            subresult = cell("checksum")

            """ # The following will work, but make it un-elidable

            setattr(ctx, "chunk_%d" % chunk_index, context())
            chunk_ctx = getattr(ctx, "chunk_%d" % chunk_index)
            macro_code_lib.map_list_N(chunk_ctx, inp_prefix, graph, chunk_inp)  #
            """

            m = macro(macro_params)
            elision = {
                "macro": m,
                "input_cells": {},
                "output_cells": {}
            }
            m.allow_elision = True

            setattr(ctx, "m{}".format(chunk_index), m)
            ctx.macro_code.connect(m.code)
            ctx.inp_prefix.connect(m.inp_prefix)
            ctx.elision_chunksize.connect(m.elision_chunksize)
            ctx.graph.connect(m.graph)
            ctx.macro_code.connect(m.map_list_N_nested_code)
            ctx.macro_code_lib.connect(m.macro_code_lib)
            ctx.macro_code_lib_code.connect(m.macro_code_lib_code)
            m.inp.cell().set(chunk_inp)
            subr = "subresult{}".format(chunk_index)
            setattr(ctx, subr, subresult)
            subresults[subr] = subresult
            result_path = path(m.ctx).result
            result_path.connect(subresult)
            elision["output_cells"][subresult] = result_path
            ctx._get_manager().set_elision(**elision)

        transformer_params = {}
        for subr in subresults:
            transformer_params[subr] = {"io": "input", "celltype": "checksum"}
        transformer_params["result"] = {"io": "output", "celltype": "checksum"}
        ctx.merge_subresults = transformer(transformer_params)
        ctx.merge_subresults.code.cell().set(merge_subresults)
        tf = ctx.merge_subresults
        for subr,c in subresults.items():
            c.connect(getattr(tf, subr))

        ctx.all_subresults = cell("plain")
        tf.result.connect(ctx.all_subresults)

        # ctx.all_subresults has the correct checksum, but there is no valid conversion
        #  (because it is unsafe).
        # Use a macro to do it

        ctx.get_result = macro({
            "result_checksum": {"io": "input", "celltype": "checksum"}
        })
        get_result = """def get_result(ctx, result_checksum):
            ctx.result = cell("mixed", hash_pattern={"!": "#"})
            ctx.result.set_checksum(result_checksum)"""
        ctx.get_result.code.cell().set(get_result)
        ctx.all_subresults.connect(ctx.get_result.result_checksum)
        p = path(ctx.get_result.ctx).result
        ctx.result = cell("mixed", hash_pattern={"!": "#"})
        p.connect(ctx.result)

    else:
        macro_code_lib.map_list_N(ctx, inp_prefix, graph, inp)
    return ctx

libctx = Context()
libctx.map_list_N = Cell("code").set(map_list_N)
libctx.map_list_N_nested = Cell("code").set(map_list_N_nested)

def main(ctx, elision_chunksize, inp_prefix, graph, map_list_N_nested_code, macro_code_lib_code, **inp):
    macro_code_lib.map_list_N_nested(
        ctx, elision_chunksize, inp_prefix, graph, inp,
        map_list_N_nested_code=map_list_N_nested_code,
        macro_code_lib_code=macro_code_lib_code,
        macro_code_lib0=macro_code_lib
    )
    return ctx

libctx.main = Cell("code").set(main)


def constructor(ctx, libctx, context_graph, inp, result, elision, elision_chunksize):
    m = ctx.m = Macro()
    m.elision = elision
    m.graph = context_graph
    m.pins.graph.celltype = "plain"
    m.pins.result = {"io": "output", "celltype": "mixed", "hash_pattern": {"!": "#"}}

    ctx.inp = Context()
    ctx.cs_inp = Context()
    inp_prefix = "INPUT_"
    m.inp_prefix = inp_prefix
    m.pins.inp_prefix.celltype = "str"
    m.elision_chunksize = elision_chunksize
    m.pins.elision_chunksize.celltype = "int"
    for key in inp:
        c = Cell()
        ctx.inp[key] = c
        c.hash_pattern = {"!": "#"}
        inp[key].connect(c)
        ctx.cs_inp[key] = Cell("checksum")
        ctx.cs_inp[key] = ctx.inp[key]
        setattr(m, inp_prefix + key , ctx.cs_inp[key])

    macro_code_lib_code = libctx.map_list_N.value + "\n\n" + libctx.map_list_N_nested.value
    macro_code_lib = {
        "type": "interpreted",
        "language": "python",
        "code": macro_code_lib_code
    }
    ctx.macro_code_lib = Cell("plain").set(macro_code_lib)
    ctx.macro_code_lib_code = Cell("code").set(macro_code_lib_code)
    m.macro_code_lib = ctx.macro_code_lib
    m.pins.macro_code_lib.celltype = "plain"
    m.pins.macro_code_lib.subcelltype = "module"
    m.macro_code_lib_code = ctx.macro_code_lib_code
    m.pins.macro_code_lib_code.celltype = "plain"
    m.map_list_N_nested_code = libctx.map_list_N_nested.value
    ###m.pins.map_list_N_nested_code.celltype = "python"

    m.code = libctx.main.value
    ctx.result = Cell()
    ctx.result.hash_pattern = {"!": "#"}
    ctx.result = m.result
    result.connect_from(ctx.result)

lib_params = {
    "context_graph": "context",
    "inp": {
        "type": "celldict",
        "io": "input"
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
libctx.lib_params = lib_params
mylib = LibraryContainer("mylib")
mylib.map_list_N = libctx
mylib.map_list_N.constructor = constructor
mylib.map_list_N.params = lib_params

ctx = Context()
ctx.adder = Context()
sctx = ctx.adder
sctx.inp = Context()
sctx.inp.a = Cell("mixed")
sctx.inp.b = Cell("mixed")
sctx.a = Cell("int")
sctx.b = Cell("int")
sctx.a = sctx.inp.a
sctx.b = sctx.inp.b
def add(a,b):
    return a+b
sctx.add = add
sctx.add.a = sctx.a
sctx.add.b = sctx.b
sctx.result = sctx.add
sctx.result.celltype = "int"
ctx.compute()

data = [
    {
        "a": 5,
        "b": 6,
    },
    {
        "a": -2,
        "b": 8,
    },
    {
        "a": 3,
        "b": 14,
    },
    {
        "a": 12,
        "b": 7,
    },
    {
        "a": 88,
        "b": -20,
    },
]
ctx.data = Cell().set(data)

def get_data_a(data):
    return [v["a"] for v in data]
ctx.get_data_a = get_data_a

def get_data_b(data):
    return [v["b"] for v in data]
ctx.get_data_b = get_data_b

ctx.get_data_a.data = ctx.data
ctx.get_data_b.data = ctx.data

ctx.data_a = Cell()
ctx.data_a.hash_pattern = {"!": "#"}
ctx.data_a = ctx.get_data_a
#ctx.compute()
#ctx.data_a.example.... # bad idea... validation forces full value construction

ctx.data_b = Cell()
ctx.data_b.hash_pattern = {"!": "#"}
#ctx.compute()
#ctx.data_b.example.... # bad idea... validation forces full value construction
ctx.data_b = ctx.get_data_b

ctx.result = Cell()
ctx.result.hash_pattern = {"!": "#"}
ctx.compute()
#ctx.result.schema.storage = "pure-plain" # bad idea... validation forces full value construction

ctx.include(mylib.map_list_N)
ctx.inst = ctx.lib.map_list_N(
    context_graph = ctx.adder,
    inp = {"a": ctx.data_a, "b": ctx.data_b},
    result = ctx.result,
    elision = True,
    elision_chunksize = 2,
)
ctx.translate(force=True)
ctx.compute()

print(ctx.result.value)
print(ctx.inst.ctx.m.exception)

print("START1")
ctx.translate(force=True)
ctx.compute()
print(ctx.result.value)
print("START2")
ctx.data.handle += [{"a": 10, "b": 0}, {"a": 12, "b": -1}, {"a": 14, "b": -2}, {"a": 16, "b": -3}]
ctx.compute(2)

print(ctx.result.value)
print(ctx.inst.ctx.m.exception)
print(ctx.inst.ctx.m.ctx.status)
