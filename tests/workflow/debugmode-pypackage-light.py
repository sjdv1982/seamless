from seamless.workflow import Context, Cell, Module
import traceback

ctx = Context()

ctx.pypackage = Module()
ctx.pypackage.multi = True
ctx.pypackage["__init__.py"] = "from .submodule import get_square"
ctx.pypackage[
    "submodule.py"
] = """
def get_square(value):
    return value**2
"""
ctx.pypackage.mount("debugmount/pypackage", authority="cell")


def func(a, b):
    from .pypackage import get_square

    aa = get_square(a)
    bb = get_square(b)
    return aa + bb


ctx.tf = func
ctx.tf.a = 10
ctx.tf.b = 20
ctx.tf.pypackage = ctx.pypackage

ctx.code = ctx.tf.code.pull()
ctx.code.mount("debugmount/debugmode-pypackage-light-code.py", authority="cell")
ctx.compute()
print(ctx.tf.result.value)

ctx.tf.debug.enable("light")
ctx.tf.a = 12
ctx.compute()
