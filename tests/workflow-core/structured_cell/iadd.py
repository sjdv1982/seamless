import seamless
seamless.delegate(False)

from seamless.workflow.core import context, cell, StructuredCell

ctx = context(toplevel=True)
ctx.data = cell("mixed")
ctx.sc = StructuredCell(
    data=ctx.data
)

data = ctx.sc.handle
data.set(20)
ctx.compute()
print(data.data, ctx.data.value)

data.set(data + 1)
ctx.compute()
print(data.data, ctx.data.value)

print(type(data))
data += 1
print(type(data))
ctx.compute()
print(data.data, ctx.data.value)
