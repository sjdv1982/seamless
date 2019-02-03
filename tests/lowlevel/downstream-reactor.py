import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, reactor, pythoncell, transformer

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.aa = cell().set(1)
    ctx.tf = transformer({
        "aa": "input",
        "a": "output"
    })
    ctx.aa.connect(ctx.tf.aa)
    ctx.code = pythoncell().set("""import time
time.sleep(2)
a = aa""")
    ctx.code.connect(ctx.tf.code)
    ctx.a = cell()    
    ctx.tf.a.connect(ctx.a)

    ctx.b = cell().set(2)
    ctx.result = cell()
    ctx.rc = reactor({
        "a": "input",
        "b": "input",
        "c": "output"
    }, pure=False) # change between pure=True/"semi"/False (default)
    ctx.a.connect(ctx.rc.a)
    ctx.b.connect(ctx.rc.b)
    ctx.code_start = pythoncell().set("")
    ctx.code_start.connect(ctx.rc.code_start)
    ctx.code_update = pythoncell().set("""
a = PINS.a.get()
b = PINS.b.get()
PINS.c.set(a+b)
    """)
    ctx.code_update.connect(ctx.rc.code_update)
    ctx.code_stop = pythoncell().set("")
    ctx.code_stop.connect(ctx.rc.code_stop)
    ctx.rc.c.connect(ctx.result)

ctx.equilibrate(1)
print(ctx.status)
ctx.equilibrate()
print(ctx.status)
print(ctx.result.value)
ctx.aa.set(10)
ctx.equilibrate(1)
print(ctx.status)
print(ctx.result.value)
ctx.equilibrate()
print(ctx.status)
print(ctx.result.value)
