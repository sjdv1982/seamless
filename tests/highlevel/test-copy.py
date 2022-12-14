from seamless.highlevel import Context, copy
ctx = Context()
ctx.tf = lambda a,b: a * b
ctx.tf.a = 3
ctx.tf.b = 4
ctx.result = ctx.tf.result
ctx.compute()

ctx2 = Context()
ctx2.tf = 0
copy(ctx.tf, ctx2.tf)
ctx.tf.a = 1000
ctx2.compute()
print(ctx2.tf.status)
print(ctx2.tf.result.value)

ctx.compute()
ctx2.subctx = 0
copy(ctx, ctx2.subctx)
ctx2.compute()
print(ctx2.subctx.tf.status)
print(ctx2.subctx.tf.result.value)

print(ctx2.tf.result.value)
ctx2.tf2 = 0
copy(ctx2.tf, ctx2.tf2)
del ctx2.tf
ctx2.compute()
print(ctx2.tf2.status)
print(ctx2.tf2.result.value)

ctx.a = 123
ctx.compute()
ctx2.aa = 0
copy(ctx.a, ctx2.aa)
ctx2.compute()
print(ctx2.aa.value)

ctx.tf.a = ctx.a
ctx.compute()
ctx2.ttf = 0
copy(ctx.tf, ctx2.ttf)
ctx2.compute()
ctx.a = 222
ctx.compute()
print(ctx.tf.result.value, ctx.a.value, ctx2.ttf.inp.value, ctx2.ttf.result.value)