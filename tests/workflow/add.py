import seamless

seamless.delegate(False)

from seamless.workflow import Context

ctx = Context()


def add(a, b):
    return a + b


ctx.a = 10
ctx.b = 20
ctx.add = add
ctx.add.a = ctx.a
ctx.add.b = ctx.b
ctx.c = ctx.add
ctx.compute()
print(ctx.c.value)

ctx.a.celltype = "plain"
ctx.a.mount("/tmp/a")
ctx.b.celltype = "plain"
ctx.b.mount("/tmp/b")
ctx.c.celltype = "plain"
ctx.c.mount("/tmp/c", mode="w")
ctx.add.code.mount("/tmp/code.py")
ctx.compute()
