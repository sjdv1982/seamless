import seamless

seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, reactor, unilink

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(1)
    ctx.cell2 = cell().set(2)
    ctx.result = cell()
    ctx.rc = reactor(
        {
            "a": "input",
            "b": "input",
            "testmodule": ("input", "plain", "module"),
            "c": "output",
        }
    )
    ctx.cell1_unilink = unilink(ctx.cell1)
    ctx.cell1_unilink.connect(ctx.rc.a)
    ctx.cell2.connect(ctx.rc.b)
    ctx.code_start = cell("reactor").set("")
    ctx.code_start.connect(ctx.rc.code_start)
    ctx.code_update = cell("reactor").set(
        """
print("reactor execute")
print(testmodule)
print(testmodule.q)
from .testmodule import q
print(q)
import sys
print([m for m in sys.modules if m.find("testmodule") > -1])

a = PINS.a.get()
b = PINS.b.get()
PINS.c.set(a+b)
print("/reactor execute")
    """
    )
    ctx.code_update.connect(ctx.rc.code_update)
    ctx.code_stop = cell("reactor").set("")
    ctx.code_stop.connect(ctx.rc.code_stop)
    ctx.result_unilink = unilink(ctx.result)
    ctx.rc.c.connect(ctx.result_unilink)

    testmodule = {"type": "interpreted", "language": "python", "code": "q = 10"}
    ctx.testmodule = cell("plain").set(testmodule)
    ctx.testmodule.connect(ctx.rc.testmodule)

ctx.compute()
print(ctx.result.value)
ctx.cell1.set(10)
ctx.compute()
print(ctx.result.value)
ctx.code_update.set(
    """
a = PINS.a.get()
b = PINS.b.get()
PINS.c.set(a+b+1000)
"""
)
ctx.compute()
print(ctx.result.value)
print(ctx.status)
