import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, reactor, pythoncell, ipythoncell

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.i = cell().set(100)
    ctx.result = cell()
    ctx.rc = reactor({
        "i": "input",
        "testmodule": ("input", "module"),
        "result": "output",
        "html": "output"
    })
    ctx.i.connect(ctx.rc.i)
    ctx.code_start = pythoncell().set("")
    ctx.code_start.connect(ctx.rc.code_start)
    ctx.code_update = pythoncell().set("""
import time
from .testmodule import func, func_html
i = PINS.i.get()
t = time.time()
result = func(i)
print("Time: %.1f" % (time.time() - t))
PINS.result.set(result)
if PINS.testmodule.updated:
    PINS.html.set(func_html)
""")
    ctx.code_update.connect(ctx.rc.code_update)
    ctx.code_stop = pythoncell().set("")
    ctx.code_stop.connect(ctx.rc.code_stop)
    ctx.rc.result.connect(ctx.result)

    ctx.testmodule = ipythoncell()
    ctx.testmodule.mount("cell-ipython.ipy")
    ctx.testmodule.connect(ctx.rc.testmodule)
    ctx.html = cell("text")
    ctx.html.mount("cell-ipython.html")
    ctx.rc.html.connect(ctx.html)
ctx.equilibrate()
print(ctx.result.value)
ctx.i.set(200)
ctx.equilibrate()
print(ctx.result.value)
print(ctx.status())
#print(ctx.testmodule.value)
