"""
Version of high-in-low5 that maps over N inputs, zipped
"""

import seamless

import seamless.core.execute
seamless.core.execute.DIRECT_PRINT = True

if seamless.delegate(level=3):
    exit(1)
seamless.set_ncores(8)
seamless.config.set_parallel_evaluations(1000)

"""
import logging
logging.basicConfig()
logging.getLogger("seamless").setLevel(logging.DEBUG)
"""

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

    def map_list_N(ctx, inp_prefix, graph, **inp):
        print("INP", inp)
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
            #print("MACRO", n+1)
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
            setattr(ctx, resultname, cell("str"))
            c = getattr(ctx, resultname)
            hc.result.connect(c)
            c.connect(ctx.sc.inchannels[(n,)])
            con = ["ctx", subctx, "result"], ["..result"]
            pseudo_connections.append(con)

        ctx.sc.outchannels[()].connect(ctx.result)
        ctx._pseudo_connections = pseudo_connections
        print("/MACRO")

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
sctx.a = Cell("mixed")  # str would be expensive!!
sctx.b = Cell("mixed")  # str would be expensive!!
sctx.a = sctx.inp.a
sctx.b = sctx.inp.b
def add(a,b):
    print("ADD", a[:10])
    return a+b
sctx.add = add
sctx.add.a = sctx.a
sctx.add.b = sctx.b
sctx.result = sctx.add
sctx.result.celltype = "str"
ctx.compute()

ctx.data_a = Cell()
ctx.data_a.hash_pattern = {"!": "#"}
ctx.data_b = Cell()
ctx.data_b.hash_pattern = {"!": "#"}
ctx.compute()

repeat = int(10e6)
#for n in range(1000): # 2x10 GB
for n in range(100): # 2x1 GB
    a = "A:%d:" % n + str(n%10) * repeat
    b = "B:%d:" % n + str(n%10) * repeat
    ctx.data_a[n] = a
    ctx.data_b[n] = b
    if n % 20 == 0:
        ctx.compute()
    print(n+1)

ctx.compute()
ctx.result = Cell()
ctx.result.hash_pattern = {"!": "#"}
ctx.compute()
#ctx.result.schema.storage = "pure-plain" # bad idea... validation forces full value construction

print(ctx.data_a._data)
print(ctx.data_a.handle[0].value[:10])
print(ctx.data_b.handle[0].value[:10])
print(ctx.data_b._data)
import time; time.sleep(1); print(); print()

ctx.include(mylib.map_list_N)
ctx.inst = ctx.lib.map_list_N(
    context_graph = ctx.adder,
    inp = {"a": ctx.data_a, "b": ctx.data_b},
    result = ctx.result
)

ctx.compute()

print("Exception:", ctx.inst.ctx.m.exception)
print(ctx.result._data)
