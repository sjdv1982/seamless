print("START")
import seamless
seamless.config.delegate(level=3)

from seamless.highlevel import Context
from seamless.core.transformation import SeamlessTransformationError
import traceback
ctx = Context()

from seamless.imperative import transformer_async

@transformer_async
def func2(a, b):
    @transformer
    def func(a, b):
        import time
        time.sleep(0.4)
        return 100 * a + b
    
    return func(a, b) + func(b, a)

ctx.tf = func2
ctx.tf.a = 21
ctx.tf.b = 17
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)
print('')

print(await func2(21,17))
print(await func2(22,18))

@transformer_async
def func2a(a, b):
    @transformer
    def func(a, b):
        import time
        time.sleep(2)
        return 100 * a + b
    #func.local = False
    
    return func(a, b) + func(b, a)

print(await func2a(29,12))

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
        #func.local = False
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

print(await func3(7,22))
print(await func3(101,720))