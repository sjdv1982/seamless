import seamless

seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, transformer

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(1)
    ctx.cell2 = cell().set(2)
    ctx.result = cell()
    ctx.tf = transformer(
        {
            "a": "input",
            "b": "input",
            "testmodule": ("input", "plain", "module"),
            "c": "output",
        }
    )
    ctx.tf._debug = {"direct_print": True}
    ctx.cell1.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = cell("transformer").set(
        """
print(testmodule)
print(testmodule.q)
from .testmodule import q
print(q)
import sys
print([m for m in sys.modules if m.find("testmodule") > -1])
c = a + b
"""
    )
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)

    testmodule = {"type": "interpreted", "language": "python", "code": "q = 10"}
    ctx.testmodule = cell("plain").set(testmodule)
    ctx.testmodule.connect(ctx.tf.testmodule)

ctx.compute()
print(ctx.result.value)

ctx.cell1.set(700)
ctx.compute()
print(ctx.result.value)
ctx.code.set("c = a + b + testmodule.q + 1000")
ctx.compute()
print(ctx.result.value)
testmodule["code"] = "q = 80"
ctx.testmodule.set(testmodule)
ctx.compute()
print(ctx.result.value)
print(ctx.status)
