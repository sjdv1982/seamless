import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, macro, transformer


mod_init = """
from .mod3 import testvalue
"""

mod1 = """
from .. import testvalue
from ..mod3 import testfunc
def func():
    return testvalue
"""

mod2 = """
from .mod1 import func
"""

mod3 = """
testvalue = 42

def testfunc(x):
    return x
"""

package = {
    "__init__": {
        "language": "python",
        "code": mod_init,
        "dependencies": [".mod3"],
    },
    "sub.__init__": {
        "language": "python",
        "code": "",
        "dependencies": [],
    },
    "sub.mod1": {
        "language": "python",
        "code": mod1,
        "dependencies": ["__init__", ".mod3"],
    },
    "sub.mod2": {
        "language": "python",
        "code": mod2,
        "dependencies": [".sub.mod1"],
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

code = """
print("execute")
from .testmodule import testvalue
from .testmodule.sub.mod1 import func
from .testmodule.sub.mod2 import func as func2
print(testvalue)
print(func is func2)
print(func2())
print(testmodule.testvalue)
from .testmodule import mod3
print(mod3.testvalue)
print(mod3.testfunc(99))
result = 0
print("/execute")
"""

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell("plain").set(1)

    ctx.macro = macro({
        "param": "plain",
        "testmodule": ("plain", "module"),
    })

    ctx.param.connect(ctx.macro.param)
    ctx.macro_code = cell("macro").set(code)
    ctx.macro_code.connect(ctx.macro.code)

    ctx.testmodule = cell("plain").set(testmodule)
    ctx.testmodule.connect(ctx.macro.testmodule)

print("START")
ctx.compute()
print(ctx.macro.exception)

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell("plain").set(1)

    ctx.tf = transformer({
        "param": {
            "io": "input",
            "celltype": "plain",
        },
        "testmodule": {
            "io": "input",
            "celltype": "plain", 
            "subcelltype": "module",
        },
        "result": "output"
    })

    ctx.param.connect(ctx.tf.param)
    ctx.tf_code = cell("transformer").set(code)
    ctx.tf_code.connect(ctx.tf.code)

    ctx.testmodule = cell("plain").set(testmodule)
    ctx.testmodule.connect(ctx.tf.testmodule)

    ctx.result = cell("plain")
    ctx.tf.result.connect(ctx.result)
    
print("START 2")
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.exception)
print(ctx.tf.status)
