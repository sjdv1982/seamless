from seamless.highlevel import Context, Cell, Macro

sctx = Context()
sctx.inp = Cell("mixed")
sctx.inp2 = Cell()
sctx.inp2 = sctx.inp
sctx.a = Cell("int")
sctx.b = Cell("int")
sctx.a = sctx.inp2.a
sctx.b = sctx.inp2.b
def add(a,b):
    return a+b
sctx.add = add
sctx.add.a = sctx.a
sctx.add.b = sctx.b
sctx.result = sctx.add
sctx.result.celltype = "int"
sctx.compute()

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

ctx = Context()
graph = sctx.get_graph(runtime=True)
ctx.graph = Cell("plain").set(graph)
ctx.data = Cell()
ctx.data.hash_pattern = {"!": "#"}
ctx.cs_data = Cell("checksum")
ctx.cs_data = ctx.data
ctx.compute()
#ctx.data.schema.storage = "pure-plain"  # bad idea... validation forces full value construction
ctx.data.set(data)
ctx.compute()
ctx.result = Cell()
ctx.result.hash_pattern = {"!": "#"}
ctx.compute()
#ctx.result.schema.storage = "pure-plain"  # bad idea... validation forces full value construction

m = ctx.m = Macro()
m.cs_data = ctx.cs_data
m.pins.cs_data.celltype = "checksum"
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
        setattr(ctx, resultname, cell("int"))
        c = getattr(ctx, resultname)
        hc.result.connect(c)
        c.connect(ctx.sc.inchannels[(n,)])

    ctx.sc.outchannels[()].connect(ctx.result)


m.code = map_list
ctx.result = m.result
ctx.compute()
print("Exception:", m.exception)
print(ctx.m.ctx.result1.value)
print(ctx.m.ctx.result2.value)
print(ctx.m.ctx.result.value)
print(ctx.m.ctx.result.data)
print()
print(ctx.m._get_mctx().result.value)
print(ctx.m._get_mctx().result.data)
print(ctx.m._get_mctx().result._hash_pattern)
print()
print(ctx.result.value)
print(ctx.result._data)
print(ctx.m.ctx.sc.status)
print(ctx.m.ctx.subctx1.a.status)
print(ctx.m.ctx.subctx1.status)
print(ctx.m.ctx.status)
print()

ctx.data.set([{"a":12, "b":-123}, {"a":182, "b":-83}])
ctx.compute()
print()
print("Exception:", m.exception)
print(ctx.m.ctx.result1.value)
print(ctx.m.ctx.result.value)
print(ctx.result.value)

def sub(a,b):
    return a-b
sctx.add.code = sub
sctx.compute()
graph = sctx.get_graph(runtime=True)
ctx.graph = Cell("plain").set(graph)
ctx.compute()
print()
print("Exception:", m.exception)
print(ctx.m.ctx.result1.value)
print(ctx.m.ctx.result.value)
print(ctx.result.value)

print()
from pprint import pprint
pprint(list(ctx._runtime_graph.nodes.keys()))