import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pymacrocell, pythoncell, macro

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell("json").set(1)

    ctx.macro = macro({
        "param": "copy",
        "testmodule": ("ref", "module", "python"),
    })

    ctx.param.connect(ctx.macro.param)
    ctx.macro_code = pymacrocell().set("""
print("macro execute")
print(testmodule)
print(testmodule.a)
from .testmodule import a
print(a)
import sys
print([m for m in sys.modules if m.find("testmodule") > -1])
print("/macro execute")
""")
    ctx.macro_code.connect(ctx.macro.code)
    ctx.testmodule = pythoncell().set("a = 10")
    ctx.testmodule.connect(ctx.macro.testmodule)


    ctx.macro2 = macro({
        "testmodule2": ("ref", "module", "python"),
    })
    ctx.macro_code2 = pymacrocell().set("""
print("macro2 execute")
print(testmodule2)
print(testmodule2.a)
from .testmodule2 import a
print(a)
import sys
print([m for m in sys.modules if m.find("testmodule") > -1])
print("/macro2 execute")
""")
    ctx.macro_code2.connect(ctx.macro2.code)
    ctx.testmodule.connect(ctx.macro2.testmodule2)

    #ctx.mount("/tmp/mount-test", persistent=None)


print("START")
ctx.equilibrate()
print("stage 1")
ctx.testmodule.set("a = 20")
print("stage 2")
ctx.macro_code.set(ctx.macro_code.value + "\npass")
