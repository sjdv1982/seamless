import seamless
from seamless.core import context, cell
seamless.delegate(level=3)
ctx = context(toplevel=True)
ctx.result = cell("mixed")
ctx.result.set_checksum("ac79945235c31685e289ad9b6f4aa0c78a09d54815d516eb2f735348c851c347")
ctx.compute()
print(ctx.result.checksum)
print(ctx.result.value)
