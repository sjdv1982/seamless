import seamless
seamless.delegate(False)

from seamless.highlevel import Context, Cell
ctx = Context()
ctx.a = Cell()

ctx.translate()
ctx.a[0] = {}
ctx.a[0]["x"] = 10
print(ctx.a.handle)
try:
    ctx.a.handle.value
    raise Exception
except AttributeError:
    pass
ctx.a[0]["y"] = 20
print(ctx.a.handle)
ctx.compute()
print(ctx.a._get_cell().auth.value)
print(ctx.a.exception)

ctx.a1x = Cell("str").set("a1x")
ctx.a1y = Cell("str").set("a1y")
ctx.a2x = "a2x"
ctx.a2y = "a2y"
ctx.a3x = 10
ctx.a3y = 20
ctx.a3z = 30
ctx.a4p = 1.2
ctx.a4q = -1.2

ctx.a[0]["x"] = ctx.a1x
ctx.a[0]["y"] = ctx.a1y
ctx.a[1]["x"] = ctx.a2x
ctx.a[1]["y"] = ctx.a2y
ctx.a[2]["x"] = ctx.a3x
ctx.a[2]["y"] = ctx.a3y
ctx.a[2]["z"] = ctx.a3z
ctx.a[3]["p"] = ctx.a4p
ctx.a[3]["q"] = ctx.a4q

ctx.aa = Cell("plain")
ctx.aa = ctx.a

ctx.compute()
print(ctx.aa.buffer.decode())
print()

ctx.a[1] = "TEST"
ctx.compute()
print(ctx.aa.buffer.decode())
