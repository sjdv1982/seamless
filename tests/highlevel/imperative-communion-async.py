raise NotImplementedError

print("START")
import os
os.environ["SEAMLESS_COMMUNION_ID"] = "test-imperative-communion"

''''
import seamless
seamless.config.block_local()

from seamless import communion_server
await communion_server.start_async()
'''

#MUST use full delegation, and so must the communion peer
### seamless.config.delegate() ### TODO

import seamless
seamless.config.block_local()
seamless.config.delegate(level=3)()

seamless.communion_server.configure_master({
    "buffer": False,
    "buffer_status": False,
    "buffer_info": False,
    "transformation_job": True,
    "transformation_status": True,
    "semantic_to_syntactic": True,
})
    
from seamless import communion_server
await communion_server.start_async()

###


from seamless.imperative import transformer_async

@transformer_async
def func(a, b):
    import time
    time.sleep(0.5)
    return 100 * a + b
func.local = False

result = await func(88, 17) # takes 0.5 sec
print(result)
result = await func(88, 17) # immediate
print(result)
result = await func(21, 17) # takes 0.5 sec
print(result)

######################

from seamless.highlevel import Context

ctx = Context()

def func(a, b):
    import time
    time.sleep(0.6)
    return 100 * a + b
ctx.tf = func
ctx.tf.meta = {"local": False}
ctx.tf.a = 21
ctx.tf.b = 17
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value)

seamless.config.unblock_local()
seamless.set_ncores(8)

def func2(a, b):
    @transformer
    def func(a, b):
        import time
        time.sleep(2)
        return 100 * a + b
    func.local = False
    
    return func(a, b) + func(b, a)

ctx.tf = func2
ctx.tf.meta = {"local": True}
ctx.tf.a = 21
ctx.tf.b = 17
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value)

# transformer within transformer within transformer...

def func3(a, b):

    @transformer
    def func2b(a, b):
        @transformer
        def func(a, b):
            import time
            time.sleep(2)
            return 100 * a + b
        func.local = False
        return func(a,b)
    func2b.local = True

    return func2b(a, b) + func2b(b, a)

ctx.tf.code = func3
ctx.tf.meta = {"local": True}
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)

ctx.tf.a = 33
ctx.tf.b = 33
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)

ctx.tf.a = 7
ctx.tf.b = 22
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)
