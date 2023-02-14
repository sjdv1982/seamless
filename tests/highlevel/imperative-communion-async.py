import seamless
###seamless.set_ncores(0)
from seamless import communion_server

seamless.database_sink.connect()
seamless.database_cache.connect()

communion_server.configure_master(
    transformation_job=True,
    transformation_status=True,
)

await communion_server.start_async()

from seamless.highlevel import Context
import json

ctx = Context()
'''
def func(a, b):
    import time
    time.sleep(0.4)
    return 100 * a + b
ctx.tf = func
ctx.tf.a = 21
ctx.tf.b = 17
await ctx.computation()
transformation_checksum = ctx.tf.get_transformation()
#print(transformation_checksum)
transformation_dict = ctx.resolve(transformation_checksum, "plain")
#print(json.dumps(transformation_dict,indent=2))
'''

##################################################

from seamless.imperative import transformer_async
seamless.set_ncores(1)

@transformer_async
def func(a, b):
    import time
    time.sleep(0.4)
    return 100 * a + b
result = await func(88, 17) # takes 0.5 sec
print(result)
result = await func(88, 17) # immediate
print(result)
result = await func(21, 17) # immediate
print(result)

##################################################

def func2(a, b):
    @transformer
    def func(a, b):
        import time
        time.sleep(0.4)
        return 100 * a + b
    
    return func(a, b) + func(b, a)

ctx.tf.meta = {"local": True}
ctx.tf.code = func2
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)

#transformation_checksum = ctx.tf.get_transformation()
#from seamless.core.cache.transformation_cache import transformation_cache
#print(transformation_cache.transformations[bytes.fromhex(transformation_checksum)])