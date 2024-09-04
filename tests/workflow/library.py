import seamless

seamless.delegate(False)

from seamless.workflow import Context
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


def constructor(ctx, libctx, result):
    graph = libctx.get_graph()
    ctx.set_graph(graph)
    if result is not None:
        result.connect_from(ctx.result)


lib.subtract.constructor = constructor
lib.subtract.params = {
    "result": {
        "io": "output",
        "type": "cell",
        "default": None,
        "must_be_defined": False,
    }
}

ctx = Context()
ctx.include(lib.subtract)
ctx.subtract1 = ctx.lib.subtract()
x = ctx.subtract1
print(x.libpath)
y = ctx.lib.subtract
print(y._path)
print(y._constructor)
print(len(y._graph))
print(len(y._graph["nodes"]))
z = lib.subtract
print(z.constructor)
print(len(z._graph))
print(len(z._zip))
print(z.ctx)
print(z.ctx.x)
print(z.ctx.x.checksum)
print(z.ctx.x.value)

ctx.compute()
print(ctx.subtract1.ctx)
print(ctx.subtract1.exception)
print(dir(ctx.subtract1.ctx))
print(ctx.subtract1.ctx.x)
print(ctx.subtract1.ctx.x.value)
print(ctx.subtract1.ctx.result.value)

ctx.result = ctx.subtract1.result
ctx.compute()
print(ctx.result.value)
