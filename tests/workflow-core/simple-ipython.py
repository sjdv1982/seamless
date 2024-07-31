import seamless
seamless.delegate(False)

from seamless.workflow.core import context, cell, transformer, unilink

ctx = context(toplevel=True)
ctx.cell1 = cell("int").set(1)
ctx.cell2 = cell("int").set(2)
ctx.code = cell("ipython").set("""
%timeit -n 10 c = a + b

%timeit -n 10 c = 99

%%timeit -n 10
def func():
    return a + b

c = a + b
""")
ctx.result = cell("int")
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})

ctx.tf.env = {
    "powers": ["ipython"]
}
ctx.cell1.connect(ctx.tf.a)
ctx.cell2.connect(ctx.tf.b)
ctx.code.connect(ctx.tf.code)
ctx.tf.c.connect(ctx.result)
ctx.compute(1)
print(ctx.cell1.value, ctx.cell1, ctx.cell1.status)
print(ctx.cell2.value, ctx.cell2, ctx.cell2.status)
print(ctx.code.value, ctx.code, ctx.code.status)
print(ctx.result.value, ctx.result, ctx.result.status)
print(ctx.tf.value, ctx.tf, ctx.tf.status)
print(ctx.status)
print(ctx.tf.exception)
ctx.compute()
exit(0)
ctx.cell1.set(10)
ctx.compute()
print(ctx.result.value, ctx.status)
