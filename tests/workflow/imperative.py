import seamless
from seamless import Checksum

seamless.delegate(False)

from seamless.workflow import Context
from seamless.workflow.core.transformation import SeamlessTransformationError
import traceback

ctx = Context()


def func(a, b):
    """Some docstring"""
    import time

    time.sleep(0.5)
    return 100 * a + b


ctx.tf = func
ctx.tf.a = 21
ctx.tf.b = 17
ctx.compute()
transformation_checksum = ctx.tf.get_transformation_checksum()
transformation_dict = ctx.resolve(transformation_checksum, "plain")

from seamless.workflow.core.direct.run import run_transformation_dict
from seamless.checksum.buffer_cache import buffer_cache

result_checksum = run_transformation_dict(transformation_dict, fingertip=False)
result = Checksum(result_checksum).resolve("mixed")

print(result)

##################################################

from seamless.direct import transformer

"""
@transformer
def func(a, b):
    import time
    time.sleep(0.5)
    return 100 * a + b
"""
func = transformer(func)

result = func(88, 17)  # takes 0.5 sec
print(result)
result = func(88, 17)  # immediate
print(result)
result = func(21, 17)  # immediate
print(result)

print("The following will give an exception:")


@transformer
def func0(a, b):
    print("START")
    raise Exception  # deliberately


try:
    func0(0, 0)
except SeamlessTransformationError:
    traceback.print_exc(1)
print("/exception")
print()
