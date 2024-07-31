import seamless
seamless.delegate(False)

import traceback
from seamless.workflow import Context, Cell
ctx = Context()
ctx.a = Cell("int").set(10)
ctx.c = Cell("int").set(30)
ctx.s = Cell()
ctx.translate()
ctx.s.a = ctx.a
ctx.s.c = ctx.c
ctx.ss = ctx.s
ctx.ss.celltype = "plain"
ctx.compute()
print(ctx.s.value)
print(ctx.ss.value)
try:
    ctx.s.set("NOT TO BE PRINTED")
except TypeError:
    traceback.print_exc()
ctx.compute()
print(ctx.s.value)
print(ctx.ss.value)
print(ctx.s.exception)
print("")
try:
    ctx.s.set("NOT TO BE PRINTED 2")
except TypeError:
    traceback.print_exc()
ctx.s.a = ctx.a
ctx.s.c = ctx.c
ctx.compute()
print(ctx.s.value)
print(ctx.ss.value)
print(ctx.s.exception)
print("")
try:
    ctx.s.set({})
except TypeError:
    traceback.print_exc()
ctx.compute()
print(ctx.s.value)
print(ctx.ss.value)
print(ctx.s.exception)
print("")
ctx.b = Cell("int").set(999)
ctx.s.b = ctx.b
ctx.compute()
print(ctx.s.value)
print(ctx.ss.value)
print(ctx.s.exception)
print("")
ctx.b = None
ctx.compute()
print(ctx.s.value)
print(ctx.ss.value)
print(ctx.s.exception)
print("")
ctx.d = 123
#ctx.d.celltype = "int" ###
ctx.s.d = ctx.d
ctx.compute()
print(ctx.s.value)
print(ctx.ss.value)
print(ctx.s.exception)
print("")
ctx.d = None
ctx.compute()
print(ctx.s.value)
print(ctx.ss.value)
print(ctx.s.exception)