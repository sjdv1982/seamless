import seamless

seamless.delegate(False)

checksum = "a768afb52fb0be2c8bf1657ea5c892df910a2a70bac7310cd8595e0f62b89fbf"  # 136
from seamless.workflow import Context

ctx = Context()
ctx.a = 10
ctx.compute()
ctx.b = 136
ctx.compute()
ctx.a.set_checksum(checksum)
ctx.compute()
print(ctx.a.value)
print(ctx.a.status)
print(ctx.a.exception)
