from seamless.highlevel import Context, Cell
from seamless.highlevel.library import stdlib
from pprint import pprint

ctx = Context()
ctx.x = 20
ctx.y = 5
ctx.minus = lambda x,y: x - y
ctx.minus.x = ctx.x
ctx.minus.y = ctx.y
ctx.result = ctx.minus
ctx.equilibrate()
print(ctx.result.value)

stdlib.subtract = ctx
def constructor(ctx, libctx, inp1, inp2, outp, const):
    graph = libctx.get_graph()
    ctx.set_graph(graph)
    inp1.connect(ctx.x)
    inp2.connect(ctx.y)
    outp.connect_from(ctx.result)
stdlib.subtract.constructor = constructor
stdlib.subtract.params = {
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
ctx.include(stdlib.subtract)
ctx.subtract1 = ctx.lib.subtract(
    inp1=ctx.a,
    inp2=ctx.b,
    outp=ctx.c,
    const=42
)

x = ctx.subtract1
print(x.libpath)
print(x.arguments)
print(x.const)
ctx.equilibrate()

print(ctx.subtract1.ctx)
print(dir(ctx.subtract1.ctx))
print(ctx.subtract1.ctx.result)
print(ctx.subtract1.ctx.result.value)
print(ctx.subtract1.ctx.minus.status)
print(ctx.c.value)

ctx.b = -120
ctx.equilibrate()
print(ctx.c.value)
ctx.bb = 999
ctx.equilibrate()
print(ctx.c.value)
ctx.subtract1.inp2 = ctx.bb
ctx.equilibrate()
print(ctx.c.value)

def constructor2(ctx, libctx, inp1, inp2, outp, const):
    graph = libctx.get_graph()
    ctx.set_graph(graph)
    inp1.connect(ctx.y)
    inp2.connect(ctx.x)
    outp.connect_from(ctx.result)
stdlib.subtract.constructor = constructor2
ctx.equilibrate()
print(ctx.c.value)
ctx.include(stdlib.subtract)
ctx.equilibrate()
print(ctx.c.value)