from seamless.highlevel import Context, Cell, Macro
from seamless.highlevel.library import LibraryContainer

mylib = LibraryContainer("mylib")
mylib.map_list = Context()
def constructor(ctx, libctx, context_graph, data, result):
    m = ctx.m = Macro()
    ctx.data = Cell()
    m.data = ctx.data
    data.connect(ctx.data)
    m.graph = context_graph
    m.pins.result = {"io": "output"}
    def map_list(ctx, data, graph):
        print("DATA", data)
        #ctx.result = cell("mixed", hash_pattern = {"!": "#"})
        ctx.result = cell("mixed") ###

        ctx.sc_data = cell("mixed") # , hash_pattern = {"!": "#"})
        ctx.sc_buffer = cell("mixed") # , hash_pattern = {"!": "#"})
        ctx.sc = StructuredCell(
            data=ctx.sc_data,
            buffer=ctx.sc_buffer,
            inchannels=[(n+1,) for n in range(len(data))],
            outchannels=[()]
            #, hash_pattern = {"!": "#"})
        )

        for n, item in enumerate(data):
            hc = HighLevelContext(graph)
            setattr(ctx, "subctx%d" % (n+1), hc)
            hc.a.set(item["a"])
            hc.b.set(item["b"])
            resultname = "result%d" % (n+1)
            setattr(ctx, resultname, cell("int"))
            c = getattr(ctx, resultname)
            hc.result.connect(c)
            c.connect(ctx.sc.inchannels[(n+1,)])

        ctx.sc.outchannels[()].connect(ctx.result)

    m.code = map_list
    ctx.result0 = Cell()
    #ctx.result0.hash_pattern = {"!": "#"}  ### TODO: BUG
    ctx.result0 = m.result
    result.connect_from(ctx.result0)


mylib.map_list.constructor = constructor
mylib.map_list.params = {
    "context_graph": "context",
    "data": {
        "type": "cell",
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
sctx.a = Cell("int")
sctx.b = Cell("int")
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

ctx.data = Cell()
#ctx.data.hash_pattern = {"!": "#"}  ### TODO: BUG
ctx.compute()
ctx.data.schema.storage = "pure-plain"
ctx.data.set(data)
ctx.result = Cell()
#ctx.result.hash_pattern = {"!": "#"}  ### TODO: BUG
ctx.compute()
ctx.result.schema.storage = "pure-plain"

ctx.include(mylib.map_list)
ctx.inst = ctx.lib.map_list(
    context_graph = ctx.adder,
    data = ctx.data,
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

ctx.data.set([{"a":12, "b":-123}, {"a":182, "b":-83}])
ctx.compute()
print()

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

print()
from pprint import pprint
pprint(list(ctx._runtime_graph.nodes.keys()))