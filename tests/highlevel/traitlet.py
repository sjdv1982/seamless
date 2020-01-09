from seamless.highlevel import Context, Cell

ctx = Context()
ctx.a = 10
#ctx.a.celltype = "plain"
ctx.translate()
t = ctx.a.traitlet()
ctx.a.set(20)
ctx.compute()
print(t.value)
t.value = 80
ctx.compute()
print(ctx.a.value)
print()

t.destroy()
ctx.a.set(-1)
ctx.compute()
print(t.value)
t.value = 90
ctx.compute()
print(t.value)
print(ctx.a.value)
