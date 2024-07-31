from seamless import transformer
from seamless.workflow import Context
from seamless.workflow.core.transformation import SeamlessTransformationError
import traceback

ctx = Context()
def func(a, b):
    import time
    time.sleep(0.5)
    return 100 * a + b
ctx.tf = func
ctx.tf.a = 21
ctx.tf.b = 17
await ctx.computation()
transformation_checksum = ctx.tf.get_transformation_checksum()
transformation_dict = ctx.resolve(transformation_checksum, "plain")

from seamless.workflow.core.direct.run import run_transformation_dict_async
from seamless.workflow.core.cache.buffer_cache import buffer_cache
from seamless.workflow.core.protocol.deserialize import deserialize_sync as deserialize

result_checksum = await run_transformation_dict_async(transformation_dict, fingertip=False)
result = deserialize(buffer_cache.get_buffer(result_checksum), result_checksum, "mixed", copy=True)
print(result)

@transformer
def func(a, b):
    import time
    time.sleep(0.5)
    return 100 * a + b
func = transformer(func)

result = func(88, 17) # takes 0.5 sec
print(result)
result = func(88, 17) # immediate
print(result)
result = func(21, 17) # immediate
print(result)

print("The following will give an exception:")
@transformer
def func0(a, b):
    print("START")
    raise Exception # deliberately
try:
    func0(0,0)
except SeamlessTransformationError:
    traceback.print_exc(1)
print("/exception")
print()
