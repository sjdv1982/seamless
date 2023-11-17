import time
from seamless.highlevel import Context

import seamless
seamless.delegate(level=3)
    
def func(a,b):
    return 201 * a + 7 * b

ctx = Context()
ctx.func = func
ctx.func.a = 4
ctx.func.b = 8
t = time.time()
ctx.compute()
print(ctx.func.result.checksum)
print(ctx.func.logs)
print(ctx.func.result.value)
print("{:.1f} seconds elapsed".format(time.time()-t))