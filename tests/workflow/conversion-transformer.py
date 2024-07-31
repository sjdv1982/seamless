import seamless
seamless.delegate(False)

from seamless.workflow import Context, Cell
ctx = Context()
ctx.a = Cell("bool").set(False)
def func(a):
    print("input", a)
    return a
ctx.tf = func
ctx.tf.a = ctx.a
ctx.tf.a.celltype = "int"
ctx.compute()
print(ctx.tf.logs)