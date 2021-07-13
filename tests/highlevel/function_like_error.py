from seamless.highlevel import Context, Cell

def func(a, b):
    return a + b

ctx = Context()
ctx.tf = func
ctx.tf.debug.direct_print = True
ctx.tf.a = 2
ctx.tf.b = 3
ctx.compute()
print(ctx.tf.result.value)
ctx.tf.code = """
import numpy as np
import random
def func(a, b):
    return np.arange(a,b)
"""
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.exception)
