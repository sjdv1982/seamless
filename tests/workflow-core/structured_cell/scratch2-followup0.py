import seamless
from seamless.workflow.core import context, cell
seamless.delegate(level=1)
ctx = context(toplevel=True)
ctx.result = cell("mixed")
ctx.result.set_checksum("ac79945235c31685e289ad9b6f4aa0c78a09d54815d516eb2f735348c851c347")
ctx.compute()
print(ctx.result.checksum)
try:
    buf = ctx.result.buffer
except seamless.CacheMissError:
    print("Buffer CANNOT be read from buffer server")
else:
    print("Buffer CAN be read from buffer server")
