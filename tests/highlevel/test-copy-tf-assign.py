from seamless.highlevel import Context
ctx = Context()
ctx.sub = Context()
ctx.sub.tf = lambda a, b: a + b
ctx.sub.tf.a = 10
ctx.sub.tf.a.celltype = "int"
ctx.sub.tf.b = 20
ctx.compute()
print(ctx.sub.tf.result.value)
ctx.tf2 = ctx.sub.tf.copy()
ctx.compute()
print(ctx.tf2.result.value)
ctx.tf2.a = 11.5
ctx.compute()
print(ctx.tf2.result.value)
ctx.a = 80
ctx.sub.tf.a = ctx.a
ctx.tf2 = ctx.sub.tf.copy()
ctx.compute()
print(ctx.tf2.result.value)
ctx.a = 90
ctx.compute()
print(ctx.tf2.result.value)
