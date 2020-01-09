import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, reactor, transformer

with open("cell-ipython.ipy", "w") as f:
    with open("cell-ipython-ORIGINAL.ipy", "r") as f2:
        f.write(f2.read())

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.i = cell().set(100)
    ctx.result = cell()
    ctx.rc = reactor({
        "i": "input",
        "testmodule": ("input", "plain", "module"),
        "result": "output",
        "html": "output"
    })
    ctx.i.connect(ctx.rc.i)
    ctx.code_start = cell("reactor").set("")
    ctx.code_start.connect(ctx.rc.code_start)
    ctx.code_update = cell("reactor").set("""
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
    ctx.code_stop = cell("reactor").set("")
    ctx.code_stop.connect(ctx.rc.code_stop)
    ctx.rc.result.connect(ctx.result)

    ctx.ipy = cell("ipython")
    ctx.ipy.mount("cell-ipython.ipy", persistent=True)
    ctx.gen_testmodule = transformer({
        "ipy": ("input", "text"),
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
    ctx.html.mount("cell-ipython.html", "w")
    ctx.rc.html.connect(ctx.html)
ctx.compute()
print(ctx.result.value)
print(ctx.status)
ctx.i.set(6000)
ctx.compute()
print(ctx.result.value)
print(ctx.status)
