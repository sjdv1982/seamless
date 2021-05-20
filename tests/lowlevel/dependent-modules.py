import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, macro

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell("plain").set(1)

    ctx.macro = macro({
        "param": "plain",
        "testmodule": ("plain", "module"),
        "dep_module": ("plain", "module"),
    })

    ctx.param.connect(ctx.macro.param)
    ctx.macro_code = cell("macro").set("""
print("macro execute")
from .testmodule import b
from .testmodule import dep
a = dep.a
from .dep_module import a as aa
print(a, b, aa)
print("/macro execute")
""")
    ctx.macro_code.connect(ctx.macro.code)

    testmodule = {
        "type": "interpreted",
        "language": "python",
        "code": """
import dep_module as dep
b = 100
        """,
        "dependencies": ["dep_module"]
    }
    ctx.testmodule = cell("plain").set(testmodule)
    ctx.testmodule.connect(ctx.macro.testmodule)

    dep_module = {
        "type": "interpreted",
        "language": "python",
        "code": "a = 10",
    }
    ctx.dep_module = cell("plain").set(dep_module)
    ctx.dep_module.connect(ctx.macro.dep_module)


print("START")
ctx.compute()
print(ctx.macro.exception)
print("stage 2")
dep_module["code"] = "a = 20"
ctx.dep_module.set(dep_module)
ctx.compute()
print(ctx.macro.exception)