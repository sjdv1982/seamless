import seamless
seamless.delegate(False)

from seamless.core import context, cell, StructuredCell

ctx = context(toplevel=True)
ctx.data = cell("mixed")
ctx.sc = StructuredCell(
    data=ctx.data
)

data = ctx.sc.handle
data.set(20)
print(data)
ctx.compute()
print(data.data, ctx.data.value)
data.set({})
data.a = "test"
data.b = 12
data.b.set(5)
data.c = {"d": {}}
data.c.d.e = 12.0
print(data)
ctx.compute()
print(data.data, ctx.data.value)
