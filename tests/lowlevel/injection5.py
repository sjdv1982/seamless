import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, reactor, transformer, pythoncell, ipythoncell

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

    ctx.ipy = ipythoncell()
    ctx.ipy.mount("cell-ipython.ipy")
    ctx.gen_testmodule = transformer({
        "ipy": ("input", "ref", "text"),
        "testmodule": "output",
    })
    ctx.ipy.connect(ctx.gen_testmodule.ipy)
    ctx.gen_testmodule.code.cell().set("""
testmodule = {
    "type": "interpreted",
    "language": "ipython",
    "code": ipy
}
    """)
    
    ctx.testmodule = cell("plain")
    ctx.gen_testmodule.testmodule.connect(ctx.testmodule)

    ctx.testmodule.connect(ctx.rc.testmodule)
    ctx.html = cell("text")
    ctx.html.mount("cell-ipython.html")
    ctx.rc.html.connect(ctx.html)
ctx.equilibrate()
print(ctx.result.value)
ctx.i.set(6000)
ctx.equilibrate()
print(ctx.result.value)
print(ctx.status)
