print("START")

import seamless
seamless.delegate()

from seamless import transformer

@transformer(return_transformation=True)
def func(a, b):
    import time
    time.sleep(0.5)
    return 100 * a + b
func.local = False

result = await func(88, 17).task() # takes 0.5 sec
print(result)
result = await func(88, 17).task() # immediate
print(result)
result = await func(21, 17).task() # takes 0.5 sec
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

@transformer(return_transformation=True)
def func3(a, b):

    @transformer
    def func2b(a, b):
        @transformer
        def func(a, b):
            import time
            time.sleep(2)
            return 100 * a + b
        return func(a,b)

    return func2b(a, b) + func2b(b, a)

result = await func3(21, 17).task()
print(result)
result = await func3(33, 33).task()
print(result)
result = await func3(7, 22).task()
print(result)