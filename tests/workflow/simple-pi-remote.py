#use with jobslave.py

import seamless
seamless.delegate()
import math
from seamless.workflow import Context, Cell
import json
ctx = Context()
ctx.pi = math.pi
ctx.doubleit = lambda a: 2 * a
ctx.doubleit.a = ctx.pi
ctx.twopi = ctx.doubleit
ctx.translate()

ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)

ctx.doubleit.code = lambda a: 42
ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)

ctx.translate(force=True)
ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)
print()

ctx.doubleit.code = lambda a: 2 * a
ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)
