import seamless
seamless.delegate(False)

from seamless.highlevel import Context

ctx = Context()

def transform(a,b):
    return a * b

ctx.tf = transform
ctx.tf.a = 12
ctx.compute()
print(ctx.tf.a.value)
print(ctx.tf["a"].value)
ctx.tf["b"] = 11
ctx.compute()
print(ctx.tf.b.value)
print(ctx.tf.result.value)
print(ctx.tf["result"].value)
