import seamless

seamless.delegate(False)

from seamless.workflow import Context, Cell
from seamless.library import LibraryContainer

lib = LibraryContainer("lib")

ctx = Context()
ctx.x = 20
ctx.y = 5
ctx.minus = lambda x, y: x - y
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
    "inp1": {"type": "cell", "io": "input"},
    "inp2": {"type": "cell", "io": "input"},
    "outp": {"type": "cell", "io": "output"},
}

ctx = Context()
ctx.a = 200
ctx.b = 120
ctx.c = Cell()
ctx.include(lib.subtract)
ctx.subtract1 = ctx.lib.subtract(inp1=ctx.a, inp2=ctx.b, outp=ctx.c, const=42)

x = ctx.subtract1
print(x.libpath)
print(x.arguments)
print(x.const)
ctx.compute()

print(ctx.subtract1.ctx)
print(dir(ctx.subtract1.ctx))
print(ctx.subtract1.ctx.result)
print(ctx.subtract1.ctx.result.value)
print(ctx.subtract1.ctx.minus.status)
print(ctx.c.value)
print()

ctx.b = -120
ctx.compute()
print(ctx.c.value)
ctx.bb = 999
ctx.compute()
print(ctx.c.value)
ctx.subtract1.inp2 = ctx.bb
ctx.compute()
print(ctx.c.value)
print()


def constructor2(ctx, libctx, inp1, inp2, outp, const):
    graph = libctx.get_graph()
    ctx.set_graph(graph)
    inp1.connect(ctx.y)
    inp2.connect(ctx.x)
    outp.connect_from(ctx.result)


lib.subtract.constructor = constructor2
ctx.compute()
print(ctx.c.value)
ctx.include(lib.subtract)
ctx.compute()
print(ctx.c.value)
