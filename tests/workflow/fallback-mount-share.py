from seamless.highlevel import Context

ctx = Context()
fctx = Context()

ctx.a = 5
ctx.a.celltype = "int"
ctx.b = 7
ctx.b.celltype = "int"
ctx.compute()

fctx.aa = 15
fctx.aa.celltype = "int"
fctx.bb = 17
fctx.bb.celltype = "int"
fctx.compute()

ctx.a.fallback(fctx.aa)
ctx.b.fallback(fctx.bb)
ctx.translate(force=True)
ctx.compute()
print(ctx.a.value, ctx.b.value)

ctx.a.mount("/tmp/a", authority="cell")
ctx.b.mount("/tmp/b", authority="cell")
ctx.a.share()
ctx.compute()
