import seamless

seamless.delegate(False)
from seamless.workflow.core.transformer import Transformer
from seamless.workflow import Context, Cell, Module, Transformer

ctx = Context()

ctx.pymodule = Module()
ctx.pymodule.code = """
def get_square(value):
    return value**2
"""
ctx.pymodule.mount("debugmount/test-pymodule.py", authority="cell")


def func(a, b):
    from .pymodule import get_square

    aa = get_square(a)
    bb = get_square(b)
    return aa + bb


ctx.tf = func
ctx.tf.a = 10
ctx.tf.b = 20
ctx.tf.pymodule = ctx.pymodule

ctx.code = ctx.tf.code.pull()
ctx.code.mount("debugmount/debugmode-pymodule-light-code.py", authority="cell")
ctx.compute()
print(ctx.tf.result.value)

ctx.tf.debug.enable("light")
ctx.tf.a = 12
ctx.compute()
print(ctx.tf.exception)
print(ctx.tf.result.value)
