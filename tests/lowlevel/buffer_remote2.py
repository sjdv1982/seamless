import seamless
from seamless.core import context, cell
seamless.delegate(level=2)()

ctx = context(toplevel=True)
ctx.d = cell("mixed").set("This is another buffer")
ctx.compute()
print(ctx.d.value)
print(ctx.d.checksum)
