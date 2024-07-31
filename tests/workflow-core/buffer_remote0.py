from seamless.core import context, cell
import numpy as np
import sys
import seamless
seamless.delegate(False)
flat = bool(int(sys.argv[1]))

ctx = context(toplevel=True)
ctx.a = cell("mixed").set("Buffer A")
ctx.b = cell("mixed").set(1234.5)
ctx.c = cell("mixed").set(np.arange(5,1934,17).astype(float)/2)
ctx.compute()
print(ctx.a.value, ctx.b.value, ctx.c.value)
ctx.save_vault("/tmp/bufferdir", flat=flat)