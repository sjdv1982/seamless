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
try:
    ctx.tf.debug.enable()
except Exception:
    traceback.print_exc(limit=0)
ctx.compute()

print()
try:
    #import os; os.environ.pop("HOSTCWD", None)
    ctx.tf.debug.enable("light")
except Exception:
    traceback.print_exc(limit=0)

print()
#ctx.tf.code.mount("debugmount/debugmode-py-light-code.py", authority="cell")
ctx.code = ctx.tf.code.pull()
ctx.code.mount("debugmount/debugmode-py-light-code.py", authority="cell")
ctx.translate()

ctx.tf.debug.enable()
assert ctx.tf.debug.mode == "light", ctx.tf.debug.mode

import traceback
print("Error 1")
try:
    ctx.translate(force=True)
except Exception:
    traceback.print_exc()
    print()

print("Error 2")
try:
    ctx.set_graph({})
except Exception:
    traceback.print_exc()
    print()

print("Error 3")
try:
    del ctx.tf
except Exception:
    traceback.print_exc()
    print()

print("START")
ctx.tf.a = 11
ctx.compute()
