"""
Version of high-in-low6 with nested invocation
"""

from seamless.highlevel import Context, Cell, Macro
from seamless.highlevel.library import LibraryContainer

def map_list_N(ctx, inp_prefix, graph, inp):
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

libctx = Context()
libctx.map_list_N = Cell("code").set(map_list_N)

def main(ctx, inp_prefix, graph, map_list_N_code, **inp):
    first_k = list(inp.keys())[0]
    length = len(inp[first_k])
    first_k = first_k[len(inp_prefix):]
    for k0 in inp:
        k = k0[len(inp_prefix):]
        if len(inp[k0]) != length:
            err = "all cells in inp must have the same length, but '{}' has length {} while '{}' has length {}"
            raise ValueError(err.format(k, len(inp[k0]), first_k, length))

    chunksize = 2 ###  # Normally, increase this quite a bit
    if length > chunksize:
        def merge_subresults(**subresults):
            result = []
            for k in sorted(subresults.keys()):
                v = subresults[k]
                result += v
            return result
        ctx.macro_code = cell("python").set(map_list_N_code)
        ctx.graph = cell("plain").set(graph)
        ctx.inp_prefix = cell("str").set(inp_prefix)
        chunk_index = 0

        macro_params = {
            'inp_prefix': {'celltype': 'str'},
            'graph': {'celltype': 'mixed'},
            'inp': {'celltype': 'plain'},
        }

        subresults = {}
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
            setattr(ctx, "m{}".format(chunk_index), m)
            ctx.macro_code.connect(m.code)
            ctx.inp_prefix.connect(m.inp_prefix)
            ctx.graph.connect(m.graph)
            m.inp.cell().set(chunk_inp)
            subr = "subresult{}".format(chunk_index)
            setattr(ctx, subr, subresult)
            subresults[subr] = subresult
            result_path = path(m.ctx).result
            result_path.connect(subresult)

        transformer_params = {}
        for subr in subresults:
            transformer_params[subr] = {"io": "input", "celltype": "checksum"}
        transformer_params["result"] = {"io": "output", "celltype": "checksum"}
        ctx.merge_subresults = transformer(transformer_params)
        ctx.merge_subresults.code.cell().set(merge_subresults)
        tf = ctx.merge_subresults
        for subr,c in subresults.items():
            c.connect(getattr(tf, subr))

        ctx.result = cell("mixed", hash_pattern={"!": "#"})
        tf.result.connect(ctx.result)

    else:
        macro_code_lib.map_list_N(ctx, inp_prefix, graph, inp)

libctx.main = Cell("code").set(main)


def constructor(ctx, libctx, context_graph, inp, result):
    m = ctx.m = Macro()
    m.graph = context_graph
    m.pins.result = {"io": "output", "celltype": "mixed", "hash_pattern": {"!": "#"}}

    ctx.inp = Context()
    ctx.cs_inp = Context()
    inp_prefix = "INPUT_"
    m.inp_prefix = inp_prefix
    m.pins.inp_prefix.celltype = "str"
    for key in inp:
        c = Cell()
        ctx.inp[key] = c
        c.hash_pattern = {"!": "#"}
        inp[key].connect(c)
        ctx.cs_inp[key] = Cell("checksum")
        ctx.cs_inp[key] = ctx.inp[key]
        setattr(m, inp_prefix + key , ctx.cs_inp[key])
        getattr(m.pins, inp_prefix + key).celltype = "checksum"

    macro_code_lib_code = libctx.map_list_N.value
    macro_code_lib = {
        "type": "interpreted",
        "language": "python",
        "code": macro_code_lib_code
    }
    ctx.macro_code_lib = Cell("plain").set(macro_code_lib)
    m.macro_code_lib = ctx.macro_code_lib
    m.pins.macro_code_lib.celltype = "module"
    m.map_list_N_code = libctx.map_list_N.value

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
]
data_a = [v["a"] for v in data]
data_b = [v["b"] for v in data]

ctx.data_a = Cell()
ctx.data_a.hash_pattern = {"!": "#"}
#ctx.compute()
#ctx.data_a.example.... # bad idea... validation forces full value construction
ctx.data_a.set(data_a)

ctx.data_b = Cell()
ctx.data_b.hash_pattern = {"!": "#"}
#ctx.compute()
#ctx.data_b.example.... # bad idea... validation forces full value construction
ctx.data_b.set(data_b)

ctx.result = Cell()
ctx.result.hash_pattern = {"!": "#"}
ctx.compute()
#ctx.result.schema.storage = "pure-plain" # bad idea... validation forces full value construction

ctx.include(mylib.map_list_N)
ctx.inst = ctx.lib.map_list_N(
    context_graph = ctx.adder,
    inp = {"a": ctx.data_a, "b": ctx.data_b},
    result = ctx.result
)
ctx.translate(force=True)
ctx.compute()

print(ctx.inst.ctx.m.exception)
print(ctx.inst.ctx.m.ctx.m1.ctx.result.value)
print(ctx.inst.ctx.m.ctx.subresult1.value)
print(ctx.inst.ctx.m.ctx.m2.ctx.result.value)
print(ctx.inst.ctx.m.ctx.subresult2.value)
print(ctx.inst.ctx.m.ctx.merge_subresults.result.cell().buffer)
print(ctx.inst.ctx.m.ctx.merge_subresults.result.cell().value)
print(ctx.inst.ctx.m.ctx.result.value)

def sub(a,b):
    return a-b
sctx.add.code = sub
ctx.compute()
print()
print(ctx.inst.ctx.m.exception)
print(ctx.inst.ctx.m.ctx.m1.ctx.result.value)
print(ctx.inst.ctx.m.ctx.subresult1.value)
print(ctx.inst.ctx.m.ctx.m2.ctx.result.value)
print(ctx.inst.ctx.m.ctx.subresult2.value)
print(ctx.inst.ctx.m.ctx.merge_subresults.result.cell().buffer)
print(ctx.inst.ctx.m.ctx.merge_subresults.result.cell().value)
print(ctx.inst.ctx.m.ctx.result.value)
