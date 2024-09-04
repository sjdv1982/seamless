"""
Library version of high-in-low4

"""

import seamless

seamless.delegate(False)

from seamless.workflow import Context, Cell, Macro
from seamless.workflow.highlevel.library import LibraryContainer

mylib = LibraryContainer("mylib")
mylib.map_list = Context()


def constructor(ctx, libctx, context_graph, data, result):
    m = ctx.m = Macro()
    ctx.data = Cell()
    ctx.data.hash_pattern = {"!": "#"}
    data.connect(ctx.data)

    ctx.cs_data = Cell("checksum")
    ctx.cs_data = ctx.data
    m.cs_data = ctx.cs_data
    m.pins.cs_data.celltype = "checksum"
    m.graph = context_graph
    m.pins.result = {"io": "output", "celltype": "mixed", "hash_pattern": {"!": "#"}}

    def map_list(ctx, cs_data, graph):
        from seamless.workflow.core import Cell as CoreCell

        print("CS-DATA", cs_data)
        pseudo_connections = []
        ctx.result = cell("mixed", hash_pattern={"!": "#"})

        ctx.sc_data = cell("mixed", hash_pattern={"!": "#"})
        ctx.sc_buffer = cell("mixed", hash_pattern={"!": "#"})
        ctx.sc = StructuredCell(
            data=ctx.sc_data,
            buffer=ctx.sc_buffer,
            inchannels=[(n,) for n in range(len(cs_data))],
            outchannels=[()],
            hash_pattern={"!": "#"},
        )

        for n, cs in enumerate(cs_data):
            hc = HighLevelContext(graph)
            subctx = "subctx%d" % (n + 1)
            setattr(ctx, subctx, hc)
            if not hasattr(hc, "inp"):
                raise TypeError("Map-reduce context must have a cell called 'inp'")
            if isinstance(hc.inp, StructuredCell):
                raise TypeError(
                    "Map-reduce context has a cell called 'inp', but its celltype must be mixed, not structured"
                )
            if not isinstance(hc.inp, CoreCell):
                raise TypeError(
                    "Map-reduce context must have an attribute 'inp' that is a cell, not a {}".format(
                        type(hc.inp)
                    )
                )
            if hc.inp.celltype != "mixed":
                raise TypeError(
                    "Map-reduce context has a cell called 'inp', but its celltype must be mixed, not {}".format(
                        hc.inp.celltype
                    )
                )

            con = ["..data"], ["ctx", subctx, "inp"]
            pseudo_connections.append(con)
            hc.inp.set_checksum(cs)
            resultname = "result%d" % (n + 1)
            setattr(ctx, resultname, cell("int"))
            c = getattr(ctx, resultname)
            hc.result.connect(c)
            c.connect(ctx.sc.inchannels[(n,)])
            con = ["ctx", subctx, "result"], ["..result"]
            pseudo_connections.append(con)

        ctx.sc.outchannels[()].connect(ctx.result)
        ctx._pseudo_connections = pseudo_connections

    m.code = map_list
    ctx.result = Cell()
    ctx.result.hash_pattern = {"!": "#"}
    ctx.result = m.result
    result.connect_from(ctx.result)


mylib.map_list.constructor = constructor
mylib.map_list.params = {
    "context_graph": "context",
    "data": {"type": "cell", "io": "input"},
    "result": {"type": "cell", "io": "output"},
}

ctx = Context()
ctx.adder = Context()
sctx = ctx.adder
sctx.inp = Cell("mixed")
sctx.inp2 = Cell()
sctx.inp2 = sctx.inp
sctx.a = Cell("int")
sctx.b = Cell("int")
sctx.a = sctx.inp2.a
sctx.b = sctx.inp2.b


def add(a, b):
    return a + b


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
ctx.data.hash_pattern = {"!": "#"}
ctx.compute()
# ctx.data.schema.storage = "pure-plain"  # bad idea... validation forces full value construction
ctx.data.set(data)
ctx.compute()
# print(ctx.data.value[0].a) # bad idea... forces full value construction
print(ctx.data.handle[0].value["a"])  # the correct way
# print(ctx.data.handle[0].a.value)  # will not work; .value has to be right after the first key (0 in this case)

ctx.result = Cell()
ctx.result.hash_pattern = {"!": "#"}
ctx.compute()
# ctx.result.schema.storage = "pure-plain" # bad idea... validation forces full value construction

ctx.include(mylib.map_list)
ctx.inst = ctx.lib.map_list(context_graph=ctx.adder, data=ctx.data, result=ctx.result)
ctx.translate(force=True)
ctx.compute()

print("Exception:", ctx.inst.ctx.m.exception)
print(ctx.inst.ctx.m.ctx.sc.value)
print(ctx.inst.ctx.m.ctx.result1.value)
print(ctx.inst.ctx.m.ctx.result2.value)
print(ctx.inst.ctx.m.ctx.result.value)
print(ctx.inst.result.value)
print(ctx.result.value)

ctx.data.set([{"a": 12, "b": -123}, {"a": 182, "b": -83}])
ctx.compute()
print()

print("Exception:", ctx.inst.ctx.m.exception)
print(ctx.inst.ctx.m.ctx.sc.value)
print(ctx.inst.ctx.m.ctx.result1.value)
print(ctx.inst.ctx.m.ctx.result2.value)
print(ctx.inst.ctx.m.ctx.result.value)
print(ctx.inst.result.value)
print(ctx.result.value)


def sub(a, b):
    return a - b


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
print()
pprint(list(ctx._runtime_graph.connections))

ctx.save_graph("/tmp/temp.seamless")
ctx.save_zip("/tmp/temp.zip")
ctx.compute()
