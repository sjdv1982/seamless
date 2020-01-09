import seamless
from seamless.core import context, cell, reactor, link

ctx = context(toplevel=True)
ctx.cell1 = cell().set(1)
ctx.cell2 = cell().set(2)
ctx.result = cell()
ctx.rc = reactor({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.cell1_link = link(ctx.cell1)
ctx.cell1_link.connect(ctx.rc.a)
ctx.cell2.connect(ctx.rc.b)
ctx.code_start = cell("reactor").set("")
ctx.code_start.connect(ctx.rc.code_start)
ctx.code_update = cell("reactor").set("""
a = PINS.a.get()
b = PINS.b.get()
PINS.c.set(a+b)
""")
ctx.code_update.connect(ctx.rc.code_update)
ctx.code_stop = cell("reactor").set("")
ctx.code_stop.connect(ctx.rc.code_stop)
ctx.result_link = link(ctx.result)
ctx.rc.c.connect(ctx.result_link)

ctx.compute()
print(ctx.result.value)
ctx.cell1.set(10)
ctx.compute()
print(ctx.result.value)
ctx.code_update.set("""
a = PINS.a.get()
b = PINS.b.get()
PINS.c.set(a+b+1000)
""")
ctx.compute()
print(ctx.result.value)
print(ctx.rc.exception)
print(ctx.status)
