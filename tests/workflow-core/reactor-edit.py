import seamless

seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, reactor, transformer

with macro_mode_on():
    ctx = context(toplevel=True)

    ctx.x = cell("int").set(2)
    ctx.y = cell("int").set(3)
    ctx.c = cell("int")
    ctx.rc = reactor(
        {
            "a": "input",
            "b": "input",
            "c": {"io": "edit", "must_be_defined": False},
        }
    )
    ctx.x.connect(ctx.rc.a)
    ctx.y.connect(ctx.rc.b)
    ctx.code_start = cell("python").set("")
    ctx.code_start.connect(ctx.rc.code_start)
    ctx.code_update = cell("python").set(
        """
if PINS.a.updated or PINS.b.updated:
    a = PINS.a.get()
    b = PINS.b.get()
    PINS.c.set(a+b)
    """
    )
    ctx.code_update.connect(ctx.rc.code_update)
    ctx.code_stop = cell("python").set("")
    ctx.code_stop.connect(ctx.rc.code_stop)
    ctx.rc.c.connect(ctx.c)

ctx.compute()
print(ctx.status)
print(ctx.c.value)
ctx.c.set(100)
ctx.compute()
print(ctx.status)
print(ctx.c.value)
ctx.c.set(102)
ctx.compute()
ctx.x.set(1000)
print("START")
print(ctx.status)
print(ctx.c.value)
ctx.compute()
print(ctx.status)
print(ctx.c.value)
