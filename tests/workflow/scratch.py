import seamless
seamless.delegate(level=3)

from seamless.workflow import Cell, Context
ctx = Context()
ctx.a = Cell("int").set(2)
ctx.b = Cell("int").set(3)
ctx.tf = lambda a,b: a+b
ctx.tf.scratch = True
ctx.tf.a = ctx.a
ctx.tf.b = ctx.b
ctx.result = ctx.tf
ctx.result.scratch = True
ctx.compute()
print(ctx.result.value)
print(ctx.result.checksum)
print(ctx.tf.exception)
ctx.result2 = Cell("str")
ctx.result2.scratch = True
ctx.result2 = ctx.result
ctx.compute()
print(ctx.result2.value)
print(ctx.result2.checksum)
