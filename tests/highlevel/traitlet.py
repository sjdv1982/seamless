from seamless.highlevel import Context, Cell

ctx = Context()
ctx.a = 10
t = ctx.a.traitlet()
ctx.a.set(20)
print(t.value)
t.value = 80
print(ctx.a.value)
