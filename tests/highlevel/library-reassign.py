from seamless.highlevel import Context, Cell
from seamless.highlevel.library import LibraryContainer
from pprint import pprint

lib = LibraryContainer("lib")

ctx = Context()
ctx.x = 20
ctx.y = 5
ctx.minus = lambda x,y: x - y
ctx.minus.x = ctx.x
ctx.minus.y = ctx.y
ctx.result = ctx.minus
ctx.compute()
print(ctx.result.value)

lib.subtract = ctx
def constructor(ctx, libctx, inp1, inp2, outp, const):
    graph = libctx.get_graph()
    ctx.set_graph(graph)
    inp1.connect(ctx.x)
    inp2.connect(ctx.y)
    outp.connect_from(ctx.result)
lib.subtract.constructor = constructor
lib.subtract.params = {
    "const": "value",
    "inp1": {
        "type": "cell",
        "io": "input"
    },
    "inp2": {
        "type": "cell",
        "io": "input"
    },
    "outp": {
        "type": "cell",
        "io": "output"
    },
}

ctx = Context()
ctx.a = 200
ctx.b = 120
ctx.c = Cell()
ctx.include(lib.subtract)
ctx.subtract = ctx.lib.subtract(
    inp1=ctx.a,
    inp2=ctx.b,
    outp=ctx.c,
    const=42
)
ctx.compute()
print(ctx.c.value)
ctx.aa = 202
ctx.bb = 121
ctx.subtract = ctx.lib.subtract(
    inp1=ctx.aa,
    inp2=ctx.bb,
    outp=ctx.c,
    const=42
)
ctx.compute()
print(ctx.c.value)
print()
