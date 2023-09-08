import seamless
seamless.config.delegate(level=3)
from seamless.highlevel import Context
import json
ctx = Context()
def func(a, b):
    import time
    time.sleep(0.4)
    return 100 * a + b
ctx.tf = func
ctx.tf.a = 21
ctx.tf.b = 17
ctx.compute()
transformation_checksum = ctx.tf.get_transformation_checksum()
#print(transformation_checksum)
transformation_dict = ctx.resolve(transformation_checksum, "plain")
#print(json.dumps(transformation_dict,indent=2))

from seamless.highlevel.direct.run import run_transformation_dict
from seamless.core.cache.buffer_cache import buffer_cache
from seamless.core.protocol.deserialize import deserialize_sync as deserialize
result_checksum = run_transformation_dict(transformation_dict, fingertip=False)

print(deserialize(buffer_cache.get_buffer(result_checksum), result_checksum, "mixed", copy=True))


##################################################

from seamless import transformer

"""
@transformer
def func(a, b):
    import time
    time.sleep(0.4)
    return 100 * a + b
"""
func = transformer(func)

result = func(88, 17) # takes 0.5 sec
print(result)
result = func(88, 17) # immediate
print(result)
result = func(21, 17) # immediate
print(result)

##################################################

@transformer
def func2(a, b):
    @transformer
    def func(a, b):
        import time
        time.sleep(0.4)
        return 100 * a + b
    
    return func(a, b) + func(b, a)


@transformer
def func3(a, b):

    @transformer
    def func2(a, b):
        @transformer
        def func(a, b):
            import time
            time.sleep(0.4)
            return 100 * a + b
        return func(a,b)

    return func2(a, b) + func2(b, a)


result = func2(86, 2) 
print(result)

result = func3(6, 13) 
print(result)

ctx.tf.code = func2
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)

# transformer within transformer within transformer...

ctx.tf.code = func3
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)
ctx.tf.a = 33
ctx.tf.b = 33
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)