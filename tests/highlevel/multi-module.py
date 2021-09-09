tf_code = '''
print(__name__)
from .testmodule import q
print(testmodule)
print(testmodule.submodule)
print(testmodule.submodule.q)
from .testmodule.submodule import q
print(q)
result = q
'''

from seamless.highlevel import Transformer, Cell, Context, Module
ctx = Context()
ctx.testmodule = Module()
ctx.testmodule.multi = True
ctx.testmodule["__init__.py"] = """
from .submodule import q
from . import submodule
""" 
ctx.testmodule["submodule.py"] = "q = 10"
ctx.testmodule.mount("/tmp/testmodule", authority="cell")

ctx.compute()
ctx.tf = Transformer()
ctx.tf.code = tf_code
ctx.tf.testmodule = ctx.testmodule
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value)

ctx.testmodule["submodule.py"] = "q = 9"
ctx.compute()
print(ctx.tf.result.value)

code = ctx.testmodule.code
print(code)
code["submodule.py"] = code["submodule.py"].replace("q = 9", "q = 80")
ctx.testmodule.set(code)
ctx.compute()
print(ctx.tf.result.value)

