from seamless.highlevel import Context, Cell

ctx = Context()
ctx.a = 0
# temp value
ctx.a += 2
ctx.compute()
print(ctx.a.value)

# structured cell
ctx.a *= 2
ctx.compute()
print(ctx.a.value)

ctx.a.celltype = "float"
ctx.compute()
print(ctx.a.value)

# simple cell
ctx.a /= 4
ctx.compute()
print(ctx.a.value)

ctx.a.celltype = "str"
ctx.compute()
print(ctx.a.value)

# simple cell
ctx.a += "!"
ctx.compute()
print(ctx.a.value)
