import seamless
seamless.delegate(level=2)
from seamless.workflow.core import context, cell

ctx = context(toplevel=True)
ctx.d = cell("mixed").set("This is another buffer")
ctx.compute()
print(ctx.d.value)
print(ctx.d.checksum)
