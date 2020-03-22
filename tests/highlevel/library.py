from seamless.highlevel import Context
from seamless.highlevel.library import LibraryContainer

stdlib = LibraryContainer("stdlib")

ctx = Context()
ctx.x = 20
ctx.y = 5
ctx.minus = lambda x,y: x - y
ctx.minus.x = ctx.x
ctx.minus.y = ctx.y
ctx.result = ctx.minus
ctx.compute()
print(ctx.result.value)

stdlib.subtract = ctx
def constructor(ctx, libctx):
    graph = libctx.get_graph()
    ctx.set_graph(graph)
stdlib.subtract.constructor = constructor
stdlib.subtract.params = {}

ctx = Context()
ctx.include(stdlib.subtract)
ctx.subtract1 = ctx.lib.subtract()
x = ctx.subtract1
print(x.libpath)
y = ctx.lib.subtract
print(y._path)
print(y._constructor)
print(len(y._graph))
z = stdlib.subtract
print(z.constructor)
print(len(z._graph))
print(len(z._zip))
print(z.ctx)
print(z.ctx.x)
print(z.ctx.x.checksum)
print(z.ctx.x.value)

ctx.compute()
print(ctx.subtract1.ctx)
print(dir(ctx.subtract1.ctx))
print(ctx.subtract1.ctx.x)
print(ctx.subtract1.ctx.x.value)
print(ctx.subtract1.ctx.result.value)