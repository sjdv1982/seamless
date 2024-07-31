from seamless.workflow import Context, Cell
ctx = Context()
ctx.a = Cell("int").set(10)
ctx.b = Cell("int").set(20)
ctx.struc = Cell()
ctx.struc.a = ctx.a
ctx.struc.b = ctx.b
ctx.aa = ctx.struc.a
ctx.bb = ctx.struc.b
ctx.compute()
print(ctx.aa.value, ctx.bb.value)
ctx.a.set(None)
ctx.compute()
print(ctx.struc.value)
print(ctx.aa.value, ctx.bb.value)

ctx.a0 = Cell("int").set(5)
def compute_a(a0):
    import time
    time.sleep(1)
    return a0
ctx.compute_a = compute_a
ctx.compute_a.a0 = ctx.a0
ctx.a = ctx.compute_a.result
ctx.compute()
print(ctx.aa.value, ctx.bb.value)
ctx.a0.set(6)
ctx.compute(0.5)
print(ctx.aa.value, ctx.bb.value, ctx.bb.status)  #FAILS: should be <Silk: None > <Silk: 20 > Status: preliminary
ctx.compute()
print(ctx.aa.value, ctx.bb.value, ctx.bb.status)
