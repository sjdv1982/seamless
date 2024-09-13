import seamless

seamless.delegate(False)

from seamless.workflow.highlevel import Context, Cell, Macro

sctx = Context()
sctx.a = Cell("int")
sctx.b = Cell("int")


def add(a, b):
    return a + b


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
ctx.compute()
ctx.data.schema.storage = "pure-plain"
ctx.data.set(data)
ctx.result = Cell()
ctx.result.hash_pattern = {"!": "#"}
ctx.compute()
ctx.result.schema.storage = "pure-plain"

m = ctx.m = Macro()
m.data = ctx.data
m.graph = ctx.graph
m.pins.result = {"io": "output", "celltype": "mixed", "hash_pattern": {"!": "#"}}


def map_list(ctx, data, graph):
    print("DATA", data)
    ctx.result = cell("mixed", hash_pattern={"!": "#"})

    ctx.sc_data = cell("mixed", hash_pattern={"!": "#"})
    ctx.sc_buffer = cell("mixed", hash_pattern={"!": "#"})
    ctx.sc = StructuredCell(
        data=ctx.sc_data,
        buffer=ctx.sc_buffer,
        inchannels=[(n,) for n in range(len(data))],
        outchannels=[()],
        hash_pattern={"!": "#"},
    )

    for n, item in enumerate(data):
        hc = HighLevelContext(graph)
        setattr(ctx, "subctx%d" % (n + 1), hc)
        hc.a.set(item["a"])
        hc.b.set(item["b"])
        resultname = "result%d" % (n + 1)
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

ctx.data.set([{"a": 12, "b": -123}, {"a": 182, "b": -83}])
ctx.compute()
print()
print("Exception:", m.exception)
print(ctx.m.ctx.result1.value)
print(ctx.m.ctx.result.value)
print(ctx.result.value)


def sub(a, b):
    return a - b


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
