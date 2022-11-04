from seamless.highlevel import Context, Cell

ctx = Context()
ctx.a = {"x": "testvalue", "y": {"a": 10, "b": 20}, "z": "constant"}
ctx.compute()
print(ctx.a.value)

ctx.x = "override"
ctx.a.x = ctx.x 
ctx.compute()
print(ctx.a.value)

del ctx.x
ctx.compute()
print(ctx.a.value)

ctx.aya = 999
ctx.a.y.a = ctx.aya
ctx.compute()
print(ctx.a.value)

del ctx.aya
ctx.compute()
print(ctx.a.value)

ctx.total = {"x": 1, "y": 2, "z": 3}
ctx.a = ctx.total
ctx.compute()
print(ctx.a.value)

del ctx.total
ctx.compute()
print(ctx.a.value)

ctx.a.q = 20
ctx.compute()
print(ctx.a.value)
