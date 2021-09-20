from seamless.core.transformer import Transformer
from seamless.highlevel import Context, Cell, Module, Transformer
import traceback

ctx = Context()

ctx.pymodule = Module()
ctx.pymodule.code = """
def get_square(value):
    return value**2
"""

def func(a, b):
    from .pymodule import get_square
    aa = get_square(a)
    bb = get_square(b)
    return aa+bb

ctx.tf = func
ctx.tf.a = 10
ctx.tf.b = 20
ctx.tf.pymodule = ctx.pymodule

ctx.code = ctx.tf.code.pull()

ctx.compute()
print(ctx.tf.result.value)

#ctx.tf.debug.attach = False
ctx.tf.debug.enable("full")

ctx.tf.a = 12
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.exception)