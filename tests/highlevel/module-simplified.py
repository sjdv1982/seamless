""" Based on tests/lowlevel/injection2.py

This is a simplified tests for modules, treating the module as a structured Cell.
In the future, this will be adapted to use highlevel Module objects
(see feature issue E5)
"""

tf_code = '''
print(testmodule)
print(testmodule.q)
from .testmodule import q
print(q)
import sys
print([m for m in sys.modules if m.find("testmodule") > -1])
c = a + b
'''

from seamless.highlevel import Transformer, Cell, Context
#import seamless.core.execute; seamless.core.execute.DIRECT_PRINT = True
ctx = Context()
ctx.testmodule = Cell("plain").set({
    "type": "interpreted",
    "language": "python",
    "code": "q = 10"
})
ctx.tf = Transformer(code=tf_code)
ctx.tf.a = 10
ctx.tf.b = 20
ctx.tf.testmodule = ctx.testmodule
ctx.tf.RESULT = "c"
ctx.tf.pins.testmodule.celltype = "plain"
ctx.tf.pins.testmodule.subcelltype = "module"
ctx.c = ctx.tf
ctx.compute()
print(ctx.testmodule.status)
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.c.value)