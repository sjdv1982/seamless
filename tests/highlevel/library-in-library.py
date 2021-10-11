from textwrap import indent
from seamless.highlevel import Context, Cell
from seamless.highlevel.library import LibraryContainer

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
def constructor(ctx, libctx, x, result):
    graph = libctx.get_graph()
    ctx.set_graph(graph)
    if x is not None:
        ctx.x = x
    if result is not None:
        result.connect_from(ctx.result)
lib.subtract.constructor = constructor
lib.subtract.params = {
    "x": {
        "io": "input",
        "type": "value",
        "default": None,
        "must_be_defined": True,
    },
    "result": {
        "io": "output",
        "type": "cell",
        "default": None,
        "must_be_defined": False,
    }
}

ctx = Context()
ctx.include(lib.subtract)
lib.subtract2 = ctx
def constructor(ctx, libctx, result):
    ctx.sub_inner = ctx.lib.subtract()
    if result is not None:
        ctx.result = ctx.sub_inner.result
        result.connect_from(ctx.result)
    else:
        ctx.result = Cell()

lib.subtract2.constructor = constructor
lib.subtract2.params = {
    "result": {
        "io": "output",
        "type": "cell",
        "default": None,
        "must_be_defined": False,
    }
}
    
ctx = Context()
ctx.include(lib.subtract2)  # will also include lib.subtract
ctx.sub_dummy = ctx.lib.subtract2()
ctx.sub_outer = ctx.lib.subtract2()
#ctx.sub_dummy = ctx.lib.subtract()
ctx.compute()

print(ctx.sub_outer.ctx)
print(ctx.sub_outer.status)
print(ctx.sub_outer.exception)
print(ctx.sub_outer.ctx.sub_inner.ctx)
print(dir(ctx.sub_outer.ctx.sub_inner.ctx))

print(ctx.sub_outer.ctx.sub_inner.ctx.x)
print(ctx.sub_outer.ctx.sub_inner.ctx.x.value)
print(ctx.sub_outer.ctx.sub_inner.ctx.result.value)


ctx.result = ctx.sub_outer.result
ctx.compute()

print(ctx.sub_outer.ctx.sub_inner.ctx.result.value)
print(ctx.sub_outer.ctx.result.status)
print(ctx.sub_outer.ctx.result.value)
print(ctx.result.value)
print(ctx.status)
ctx.compute()
ctx.subcontext = Context()
ctx.subcontext.sub1 = ctx.lib.subtract()
ctx.subcontext.result = ctx.subcontext.sub1.result
ctx.compute()
print("SUB", 1, ctx.subcontext.result.value)
ctx.subcontext.sub1.x = 12
ctx.compute()
print(ctx.subcontext.sub1.exception)
print(ctx.subcontext.sub1.ctx.x.value)
print("SUB", 2, ctx.subcontext.result.value)
ctx.subcontext2 = ctx.subcontext
ctx.compute()
print(ctx.subcontext.sub1.exception)
print("SUB", 3, ctx.subcontext.result.value)
print(ctx.subcontext2.sub1.exception)
print("SUB", 4, ctx.subcontext2.result.value)
ctx.subcontext2.sub1.x = 100
ctx.compute()
print("SUB", 5, ctx.subcontext.result.value)
print("SUB", 6, ctx.subcontext2.result.value)
