import seamless

seamless.delegate(False)
from seamless.workflow import Context, Cell

ctx = Context()


def func(a, b):
    aa = a**2
    bb = b**2
    return aa + bb


ctx.tf = func
ctx.tf.a = 10
ctx.tf.b = 20
ctx.compute()
ctx.tf.debug.attach = False
ctx.tf.debug.enable("sandbox")
ctx.tf.debug.shell()
