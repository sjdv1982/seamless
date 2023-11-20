"""
Version of high-in-low5 that maps over N inputs, zipped
"""

import seamless
seamless.delegate(False)

from seamless.highlevel import Context, Cell, Macro
from seamless.highlevel.library import LibraryContainer

mylib = LibraryContainer("mylib")
mylib.map_list_N = Context()
def constructor(ctx, libctx, context_graph, inp, result):
    m = ctx.m = Macro()
    m.graph = context_graph
    m.pins.result = {"io": "output", "celltype": "mixed", "hash_pattern": {"!": "#"}}

    ctx.inp = Context()
    ctx.cs_inp = Context()
    inp_prefix = "INPUT_"
    m.inp_prefix = inp_prefix
    for key in inp:
        c = Cell()
        ctx.inp[key] = c
        c.hash_pattern = {"!": "#"}
        inp[key].connect(c)
        ctx.cs_inp[key] = Cell("checksum")
        ctx.cs_inp[key] = ctx.inp[key]
        setattr(m, inp_prefix + key , ctx.cs_inp[key])
        getattr(m.pins, inp_prefix + key).celltype = "checksum"

    def map_list_N(ctx, inp_prefix, graph, **inp):
        first_k = list(inp.keys())[0]
        length = len(inp[first_k])
        first_k = first_k[len(inp_prefix):]
        for k0 in inp:
            k = k0[len(inp_prefix):]
            if len(inp[k0]) != length:
                err = "all cells in inp must have the same length, but '{}' has length {} while '{}' has length {}"
                raise ValueError(err.format(k, len(inp[k0]), first_k, length))

        from seamless.core import Cell as CoreCell
        from seamless.core.unbound_context import UnboundContext
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

    m.code = map_list_N
    ctx.result = Cell()
    ctx.result.hash_pattern = {"!": "#"}
    ctx.result = m.result
    result.connect_from(ctx.result)


mylib.map_list_N.constructor = constructor
mylib.map_list_N.params = {
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

print("Exception:", ctx.inst.ctx.m.exception)
print(ctx.inst.ctx.m.ctx.sc.value)
print(ctx.inst.ctx.m.ctx.result1.value)
print(ctx.inst.ctx.m.ctx.result2.value)
print(ctx.inst.ctx.m.ctx.result.value)
print(ctx.inst.result.value)
print(ctx.result.value)

def sub(a,b):
    return a-b
sctx.add.code = sub
ctx.compute()
print()

print("Exception:", ctx.inst.ctx.m.exception)
print(ctx.inst.ctx.m.ctx.sc.value)
print(ctx.inst.ctx.m.ctx.result1.value)
print(ctx.inst.ctx.m.ctx.result2.value)
print(ctx.inst.ctx.m.ctx.result.value)
print(ctx.inst.result.value)
print(ctx.result.value)
