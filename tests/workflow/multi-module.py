import seamless

seamless.delegate(False)

tf_code = """
print(__name__)
from .testmodule import q
print(testmodule)
print(testmodule.submodule)
print(testmodule.submodule.q)
from .testmodule.submodule import q
print(q)
result = q
"""

from seamless.workflow import Transformer, Context, Module

ctx = Context()
ctx.testmodule = Module()
ctx.testmodule.multi = True
ctx.testmodule[
    "__init__.py"
] = """
from .submodule import q
from . import submodule
"""
ctx.testmodule[
    "submodule.py"
] = """q = 10
def func():
    return 42
"""
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

ctx.testmodule[
    "submodule.py"
] = """q = 9
def func():
    return 42
"""
ctx.compute()
print(ctx.tf.result.value)

code = ctx.testmodule.code
print(code)
code["submodule.py"] = code["submodule.py"].replace("q = 9", "q = 80")
ctx.testmodule.set(code)
ctx.compute()
print(ctx.tf.result.value)

ctx.testmodule[
    "submodule2.py"
] = """
from mytestmodule.submodule import q, func
q2 = 2 * q
"""
ctx.testmodule.internal_package_name = "mytestmodule"
ctx.tf.code = """
from .testmodule.submodule2 import q2, func
func()
result = q2
"""
ctx.compute()
print(ctx.tf.exception)
print(ctx.tf.result.value)

# For interactive testing, paste the following code into IPython:
'''
import random
ctx.tf.debug.direct_print = True
ctx.tf.code.mount("/tmp/multi-module-script.py", authority="cell")
ctx.compute()
ctx.tf.debug.enable("light")
ctx.compute()
ctx.tf.code = """from .testmodule.submodule2 import q2, func
func()
result = q2 + """ + str(random.random())

# open /tmp/multi-module-script.py and /tmp/testmodule/* in VSCode, and set breakpoints.
# NOTE: in modules, since they are pre-imported, you can set breakpoints only inside functions!
'''
