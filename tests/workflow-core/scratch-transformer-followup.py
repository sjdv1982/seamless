import seamless
from seamless.workflow.core import context, cell
seamless.delegate(level=1)
ctx = context(toplevel=True)
ctx.result = cell("mixed")
ctx.result.set_checksum("8643002a41c874e22124d5abbc2fac3d5153ec3b5012672d6e81c6e5dca475a1")
ctx.compute()
print(ctx.result.checksum)
try:
    buf = ctx.result.buffer
except seamless.CacheMissError:
    print("Buffer CANNOT be read from buffer server")
else:
    print("Buffer CAN be read from buffer server")
