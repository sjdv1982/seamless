import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, macro


mod_init = """
from .mod3 import testvalue
"""

mod1 = """
from . import testvalue
def func():
    return testvalue
"""

mod2 = """
from .mod1 import func
"""

mod3 = """
testvalue = 42
"""

package = {
    "__init__": {
        "language": "python",
        "code": mod_init,
        "dependencies": [".mod3"],
    },
    "mod1": {
        "language": "python",
        "code": mod1,
        "dependencies": ["__init__"],
    },
    "mod2": {
        "language": "python",
        "code": mod2,
        "dependencies": [".mod1"],
    },
    "mod3": {
        "language": "python",
        "code": mod3,
        "dependencies": [],
    },
}

testmodule = {
    "type": "interpreted",
    "language": "python",
    "code": package,
}

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell("plain").set(1)

    ctx.macro = macro({
        "param": "plain",
        "testmodule": ("plain", "module"),
    })

    ctx.param.connect(ctx.macro.param)
    ctx.macro_code = cell("macro").set("""
print("macro execute")
from .testmodule import testvalue
from .testmodule.mod1 import func
from .testmodule.mod2 import func as func2
print(testvalue)
print(func is func2)
print(func2())
print(testmodule.testvalue)
from .testmodule import mod3
print(mod3.testvalue)
print("/macro execute")
""")
    ctx.macro_code.connect(ctx.macro.code)

    ctx.testmodule = cell("plain").set(testmodule)
    ctx.testmodule.connect(ctx.macro.testmodule)

print("START")
ctx.compute()
print(ctx.macro.exception)
