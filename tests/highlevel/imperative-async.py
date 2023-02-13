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

##################################################

def func2(a, b):

    @transformer
    def func(a, b):
        import time
        time.sleep(0.5)
        return 100 * a + b
    
    return func(a, b) + func(b, a)

ctx.tf.code = func2
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)

# transformer within transformer within transformer...

def func3(a, b):

    @transformer
    def func2(a, b):
        @transformer
        def func(a, b):
            import time
            time.sleep(0.5)
            return 100 * a + b
        return func(a,b)

    return func2(a, b) + func2(b, a)

ctx.tf.code = func3
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)

ctx.tf.a = 33
ctx.tf.b = 33
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
