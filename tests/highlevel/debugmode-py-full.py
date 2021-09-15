from seamless.highlevel import Context, Cell

ctx = Context()

def func(a, b):
    aa = a**2
    bb = b**2
    return aa+bb

ctx.tf = func
ctx.tf.a = 10
ctx.tf.b = 20
ctx.result = ctx.tf.result
ctx.compute()
print(ctx.tf.result.value, ctx.result.value)

ctx.tf.debug.attach = False
ctx.tf.debug.enable()
ctx.compute()
print(ctx.tf.result.value, ctx.result.value)
ctx.tf.a = 11
ctx.compute()
print(ctx.tf.result.value, ctx.result.value)
ctx.tf.debug.pull()
ctx.compute()
print(ctx.tf.result.value, ctx.result.value)

#ctx.tf.debug.disable()
ctx.tf.debug.attach = True
#ctx.tf.debug.enable()
ctx.tf.a = 99
ctx.compute()
print(ctx.tf.result.value, ctx.result.value)
