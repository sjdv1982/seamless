""" Based on tests/lowlevel/injection2.py

This is a simplified test for modules, treating the module as a structured Cell.
"""

import seamless
seamless.delegate(False)

tf_code = '''
print(__name__)
print(testmodule)
print(testmodule.q)
from .testmodule import q
print(q)
import sys
print([m for m in sys.modules if m.find("testmodule") > -1])
result = a + b
'''

from seamless.highlevel import Transformer, Cell, Context
ctx = Context()
ctx.testmodule = Cell("plain").set({
    "type": "interpreted",
    "language": "python",
    "code": "q = 10"
})
ctx.tf = Transformer(code=tf_code)
ctx.tf.a = 10
ctx.tf.b = 20
ctx.tf.debug.direct_print = True
ctx.tf.testmodule = ctx.testmodule
ctx.tf.pins.testmodule.celltype = "module"
ctx.c = ctx.tf
ctx.compute()
print(ctx.testmodule.status)
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.c.value)