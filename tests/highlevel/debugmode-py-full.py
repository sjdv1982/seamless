from seamless.highlevel import Context, Cell
import traceback

ctx = Context()

def func(a, b):
    aa = a**2
    bb = b**2
    return aa+bb

ctx.tf = func
ctx.tf.a = 10
ctx.tf.b = 20
ctx.result = ctx.tf.result
ctx.compute()

ctx.tf.debug.attach = False
ctx.tf.debug.enable()
ctx.tf.a = 11
ctx.compute()

