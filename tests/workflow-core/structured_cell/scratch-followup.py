import seamless

seamless.delegate(level=3)
from seamless.workflow.core import context, cell

ctx = context(toplevel=True)
ctx.result = cell("mixed")
ctx.result.set_checksum(
    "8643002a41c874e22124d5abbc2fac3d5153ec3b5012672d6e81c6e5dca475a1"
)
ctx.compute()
print(ctx.result.checksum)
try:
    v = ctx.result.value
    print(v["a"][:20], v["b"][:20], v["c"][:20])
except seamless.CacheMissError:
    print("CacheMissError")
