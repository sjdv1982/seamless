import seamless

seamless.delegate(False)

tf_code = """
print(__name__)
print(testmodule)
print(testmodule.q)
from .testmodule import q
print(q)
import sys
print([m for m in sys.modules if m.find("testmodule") > -1])
result = a + b
"""

from seamless.workflow import Transformer, Cell, Context, Module

ctx = Context()
ctx.testmodule = Module()
ctx.testmodule.code = "q = 10"

ctx.compute()
print(ctx.testmodule.type)
print(ctx.testmodule.language)
print(ctx.testmodule.code)

ctx.a = Cell("text").set("a=42")
ctx.testmodule = ctx.a
ctx.compute()
print(ctx.testmodule.code)
ctx.a = "a=43"
ctx.compute()
print(ctx.testmodule.code)

ctx.testmodule.code = "q = 9"
ctx.compute()
print(ctx.testmodule.code)

ctx.testmodule.set("q = 12")
ctx.compute()
print(ctx.testmodule.code)

ctx.mod = ctx.testmodule
ctx.compute()
print(ctx.mod.value)

ctx.testmodule.mount("/tmp/x.py", authority="cell")
ctx.compute()


def tf(a):
    from .mymodule import q

    return a * q * mymodule.q


ctx.tf = tf
ctx.tf.debug.direct_print = True
ctx.tf.a = 10
ctx.tf.mymodule = ctx.testmodule
ctx.compute()
print(ctx.tf.result.value)
