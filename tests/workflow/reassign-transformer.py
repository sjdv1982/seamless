import seamless
seamless.delegate(False)

from seamless.highlevel import Context
ctx = Context()

def func(a,b,c,x):
    return a + b + 10 * c - x

ctx.tf = func
ctx.a = 10    
ctx.b = 20
ctx.tf.a = ctx.a
ctx.tf.b = ctx.b
ctx.tf.c = 80
ctx.tf.x = 123
ctx.compute()
def func2(b,c,d):
    return b + 10 * c - d
ctx.tf = func2
ctx.tf.d = 5
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.inp.value)
print(ctx.tf.result.value)

graph = ctx.get_graph()

dummy = Context()
dummy.c = graph
dummy.c.celltype = "plain"
dummy.compute()
print(dummy.c.checksum)

ctx = Context()
ctx.tf = func2
ctx.a = 10
ctx.b = 20
ctx.tf.b = ctx.b
ctx.tf.c = 80
ctx.tf.d = 5
ctx.tf.inp.x = 123

ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.inp.value)
print(ctx.tf.result.value)

graph = ctx.get_graph()
dummy.c = graph
dummy.compute()
print(dummy.c.checksum)
