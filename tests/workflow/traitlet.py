import seamless
seamless.delegate(False)

from seamless.highlevel import Context, Cell
import time

ctx = Context()
ctx.a = 10
#ctx.a.celltype = "plain"
ctx.translate()
t = ctx.a.traitlet()
ctx.a.set(20)
ctx.compute()
print(t.value)
t.value = 80
time.sleep(0.2) #value update takes 0.1 sec
ctx.compute()
print(ctx.a.value)
print()

t.destroy()
ctx.a.set(-1)
ctx.compute()
print(t.value)
t.value = 90
ctx.compute()
print(t.value)
print(ctx.a.value)
