from seamless.highlevel import Context
import json
ctx = Context()
def func(a, b):
    import time
    time.sleep(0.5)
    return 100 * a + b
ctx.tf = func
ctx.tf.a = 21
ctx.tf.b = 17
await ctx.computation()
transformation_checksum = ctx.tf.get_transformation()
transformation_dict = ctx.resolve(transformation_checksum, "plain")

from seamless.imperative import run_transformation_dict_async
result = await run_transformation_dict_async(transformation_dict)
print(result)

##################################################

from seamless.imperative import transformer_async

@transformer_async
def func(a, b):
    import time
    time.sleep(0.5)
    return 100 * a + b

result = await func(88, 17) # takes 0.5 sec
print(result)
result = await func(88, 17) # immediate
print(result)
result = await func(21, 17) # immediate
print(result)