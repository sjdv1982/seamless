import seamless

import seamless.core.execute
seamless.core.execute.DIRECT_PRINT = True

seamless.database_sink.connect()
seamless.database_cache.connect()
seamless.set_ncores(2)
seamless.set_parallel_evaluations(5)

"""
import logging
logging.basicConfig()
logging.getLogger("seamless").setLevel(logging.DEBUG)
"""

from seamless.highlevel import Context, Cell, Macro

sctx = Context()
sctx.inp = Cell("mixed")
sctx.inp2 = Cell()
sctx.inp2 = sctx.inp
sctx.a = Cell("str")
sctx.b = Cell("str")
sctx.a = sctx.inp2.a
sctx.b = sctx.inp2.b
def add(a,b):
    print("ADD", a[:10], b[:10])
    return a+b
sctx.add = add
sctx.add.a = sctx.a
sctx.add.b = sctx.b
sctx.result = sctx.add
sctx.result.celltype = "str"
sctx.compute()


ctx = Context()
graph = sctx.get_graph(runtime=True)
ctx.graph = Cell("plain").set(graph)
ctx.data = Cell()
ctx.data.hash_pattern = {"!": "#"}
ctx.compute()
#ctx.data.schema.storage = "pure-plain" # bad idea... validation forces full value construction

repeat = int(10e6)
#for n in range(1000): # 2x10 GB
for n in range(100): # 2x1 GB
    a = "A:%d:" % n + str(n%10) * repeat
    b = "B:%d:" % n + str(n%10) * repeat
    ctx.data[n] = {}
    #ctx.data[n].a = a   # bad idea, forces full value construction
    #ctx.data[n].b = b   # bad idea, forces full value construction
    ctx.data[n] = {"a": a, "b": b}  # much better
    if n % 20 == 0:
        ctx.compute()
    print(n+1)

ctx.compute()
print(ctx.data.data)
import time; time.sleep(1); print(); print()

ctx.cs_data = Cell("checksum")
ctx.cs_data = ctx.data
ctx.result = Cell()
ctx.result.hash_pattern = {"!": "#"}
ctx.compute()
#ctx.result.schema.storage = "pure-plain" # bad idea... validation forces full value construction

m = ctx.m = Macro()
m.cs_data = ctx.cs_data
m.graph = ctx.graph
m.pins.result = {"io": "output", "celltype": "mixed", "hash_pattern": {"!": "#"}}
def map_list(ctx, cs_data, graph):
    from seamless.core import Cell as CoreCell
    print("CS-DATA", cs_data)
    ctx.result = cell("mixed", hash_pattern = {"!": "#"})

    ctx.sc_data = cell("mixed" , hash_pattern = {"!": "#"})
    ctx.sc_buffer = cell("mixed" , hash_pattern = {"!": "#"})
    ctx.sc = StructuredCell(
        data=ctx.sc_data,
        buffer=ctx.sc_buffer,
        inchannels=[(n,) for n in range(len(cs_data))],
        outchannels=[()],
        hash_pattern = {"!": "#"}
    )

    for n, cs in enumerate(cs_data):
        hc = HighLevelContext(graph)
        setattr(ctx, "subctx%d" % (n+1), hc)
        if not hasattr(hc, "inp"):
            raise TypeError("Map-reduce context must have a cell called 'inp'")
        if isinstance(hc.inp, StructuredCell):
            raise TypeError("Map-reduce context has a cell called 'inp', but its celltype must be mixed, not structured")
        if not isinstance(hc.inp, CoreCell):
            raise TypeError("Map-reduce context must have an attribute 'inp' that is a cell, not a {}".format(type(hc.inp)))
        if hc.inp.celltype != "mixed":
            raise TypeError("Map-reduce context has a cell called 'inp', but its celltype must be mixed, not {}".format(hc.inp.celltype))
        hc.inp.set_checksum(cs)
        resultname = "result%d" % (n+1)
        setattr(ctx, resultname, cell("str"))
        c = getattr(ctx, resultname)
        hc.result.connect(c)
        c.connect(ctx.sc.inchannels[(n,)])

    ctx.sc.outchannels[()].connect(ctx.result)


m.code = map_list
ctx.result = m.result
ctx.compute()
print("Exception:", m.exception)
print(ctx.result.data)