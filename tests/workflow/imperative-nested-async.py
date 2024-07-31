print("START")
import seamless
seamless.delegate(level=3)

from seamless.workflow import Context
ctx = Context()

from seamless import transformer

@transformer(return_transformation=True)
def func2(a, b):
    @transformer(return_transformation=True)
    def func(a, b):
        import time
        time.sleep(0.4)
        return 100 * a + b
    t1 = func(a,b)
    t1.start()
    t2 = func(b,a)
    t2.start()
    t1.compute()
    t2.compute()
    return t1.value + t2.value

ctx.tf = func2
ctx.tf.a = 21
ctx.tf.b = 17
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)
print('')

print(await func2(21,17).task())
print(await func2(22,18).task())

@transformer(return_transformation=True)
def func2a(a, b):
    @transformer(return_transformation=True)
    def func(a, b):
        import time
        time.sleep(2)
        return 100 * a + b
    #func.local = False
    
    t1 = func(a,b)
    t1.start()
    t2 = func(b,a)
    t2.start()
    t1.compute()
    t2.compute()
    return t1.value + t2.value

print(await func2a(29,12).task())

# transformer within transformer within transformer...

@transformer(return_transformation=True)
def func3(a, b):
    @transformer(return_transformation=True)
    def func2b(a, b):
        @transformer(return_transformation=True)
        def func(a, b):
            import time
            time.sleep(2)
            return 100 * a + b
        #func.local = False
        
        return func(a,b).compute().value
    #func2b.local = True

    t1 = func2b(a,b)
    t1.start()
    t2 = func2b(b,a)
    t2.start()
    t1.compute()
    t2.compute()
    return t1.value + t2.value

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

print(await func3(7,22).task())
print(await func3(101,720).task())