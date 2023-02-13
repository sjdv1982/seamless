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
###ctx.compute()
await ctx.computation()
transformation_checksum = ctx.tf.get_transformation()
#print(transformation_checksum)
transformation_dict = ctx.resolve(transformation_checksum, "plain")
#print(json.dumps(transformation_dict, indent=2))

'''
from seamless.imperative import run_transformation_dict
result = run_transformation_dict(transformation_dict)
print(result)
'''

from seamless.imperative import run_transformation_dict_async
result = await run_transformation_dict_async(transformation_dict)
print(result)


##################################################

from seamless.imperative import transformer, transformer_async

'''

"""
@transformer
def func(a, b):
    import time
    time.sleep(0.5)
    return 100 * a + b
"""
func = transformer(func)
'''

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

##################################################

def func2(a, b):

    from seamless.imperative import transformer
    @transformer
    def func(a, b):
        import time
        time.sleep(0.5)
        return 100 * a + b
    
    return func(a, b) + func(b, a)

ctx.tf.code = func2
###ctx.compute()
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)