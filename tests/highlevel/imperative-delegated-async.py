print("START")
import os
os.environ["SEAMLESS_ASSISTANT_ID"] = "test-imperative-communion"

import seamless
seamless.config.delegate()

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
    ###func.local = False
    
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

@transformer_async
def func3(a, b):

    @transformer
    def func2b(a, b):
        @transformer
        def func(a, b):
            import time
            time.sleep(2)
            return 100 * a + b
        ###func.local = False
        return func(a,b)
    func2b.local = True

    return func2b(a, b) + func2b(b, a)

result = await func3(21, 17)
print(result)
result = await func3(33, 33)
print(result)
result = await func3(7, 22)
print(result)