import seamless
from seamless.core import context, cell, transformer, unilink

ctx = context(toplevel=True)
ctx.cell1 = cell().set(1)
ctx.cell2 = cell().set(2)    
ctx.result = cell()
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.cell1_unilink = unilink(ctx.cell1)
ctx.cell1_unilink.connect(ctx.tf.a)    
ctx.cell2.connect(ctx.tf.b)
ctx.code = cell("transformer").set("a + b")
ctx.code.connect(ctx.tf.code)
ctx.result_unilink = unilink(ctx.result)
ctx.tf.c.connect(ctx.result_unilink)

print(ctx.cell1.value)
ctx.compute()
print(ctx.result.value, ctx.status)
ctx.cell1.set(10)
ctx.compute()
print(ctx.result.value, ctx.status)
ctx.code.set("a + b + 1000")
ctx.compute()
print(ctx.result.value, ctx.status)

def func(a,b):
    from seamless import pdb; pdb.set_trace()
    return a + b + 2000
ctx.code.set(func)
ctx.compute(report=None)
print(ctx.result.value, ctx.status)
