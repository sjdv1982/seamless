import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer

with open("cell-ipython.ipy", "w") as f:
    with open("cell-ipython-ORIGINAL.ipy", "r") as f2:
        f.write(f2.read())

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.i = cell().set(100)
    ctx.result = cell()
    ctx.tf = transformer({
        "i": "input",
        "testmodule": ("input", "plain", "module"),
        "result": "output",
    })
    ctx.tf._debug = {
        "direct_print" : True
    }
    ctx.gen_html = transformer({
        "testmodule": ("input", "plain", "module"),
        "html": "output",
    })

    ctx.i.connect(ctx.tf.i)
    ctx.code = cell("python").set("""
import time
from .testmodule import func, func_html
t = time.time()
result = func(i)
print("Time: %.1f" % (time.time() - t))
""")
    ctx.code.connect(ctx.tf.code)
    ctx.tf.result.connect(ctx.result)

    def gen_html():
        from .testmodule import func, func_html
        return func_html
    ctx.code2 = cell("python").set(gen_html)
    ctx.code2.connect(ctx.gen_html.code)

    ctx.ipy = cell("ipython")
    ctx.ipy.mount("cell-ipython.ipy")
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
    ctx.testmodule.connect(ctx.tf.testmodule)
    ctx.testmodule.connect(ctx.gen_html.testmodule)

    ctx.html = cell("text")
    ctx.html.mount("cell-ipython.html", "w")
    ctx.gen_html.html.connect(ctx.html)
ctx.compute()
print(ctx.result.value)

ctx.i.set(6000)
ctx.compute()
print(ctx.result.value)
print(ctx.status)

with open("cell-ipython.ipy", "w") as f:
    with open("cell-ipython-OPTIMIZED.ipy", "r") as f2:
        f.write(f2.read())


import asyncio
fut = asyncio.ensure_future(asyncio.sleep(0.5))
asyncio.get_event_loop().run_until_complete(fut)
ctx.compute()
print(ctx.result.value)
