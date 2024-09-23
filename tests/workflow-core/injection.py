import seamless

seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, transformer, macro

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell("plain").set(1)

    ctx.macro = macro(
        {
            "param": "plain",
            "testmodule": ("plain", "module"),
        }
    )

    ctx.param.connect(ctx.macro.param)
    ctx.macro_code = cell("macro").set(
        """
print("macro execute")
print(testmodule)
print(testmodule.a)
from .testmodule import a
print(a)
import sys
print([m for m in sys.modules if m.find("testmodule") > -1])
print("/macro execute")
"""
    )
    ctx.macro_code.connect(ctx.macro.code)
    testmodule = {"type": "interpreted", "language": "python", "code": "a = 10"}
    ctx.testmodule = cell("plain").set(testmodule)
    ctx.testmodule.connect(ctx.macro.testmodule)

    ctx.macro2 = macro(
        {
            "testmodule2": ("plain", "module"),
        }
    )
    ctx.macro_code2 = cell("macro").set(
        """
print("macro2 execute")
print(testmodule2)
print(testmodule2.a)
from .testmodule2 import a
print(a)
import sys
print([m for m in sys.modules if m.find("testmodule") > -1])
print("/macro2 execute")
"""
    )
    ctx.macro_code2.connect(ctx.macro2.code)
    ctx.testmodule.connect(ctx.macro2.testmodule2)


print("START")
ctx.compute()
print("stage 1")
testmodule["code"] = "a = 20"
ctx.testmodule.set(testmodule)
ctx.compute()
print("stage 2")
ctx.macro_code.set(ctx.macro_code.value + "\npass")
ctx.compute()
