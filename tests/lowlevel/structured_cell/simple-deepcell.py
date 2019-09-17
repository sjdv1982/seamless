from seamless.core import context, cell, StructuredCell

ctx = context(toplevel=True)
ctx.data = cell("mixed")
ctx.sc = StructuredCell(
    data=ctx.data,
    hash_pattern= {"*":"#"}
)

data = ctx.sc.handle
data.set(20)

data.x.set("test")
print(data)