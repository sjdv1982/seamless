import seamless
#seamless.set_ncores(0)
from seamless import communion_server

seamless.database_sink.connect()
seamless.database_cache.connect()

communion_server.configure_master(
    transformation_job=True,
    transformation_status=True,
)

communion_server.start()

from seamless.highlevel import Context

ctx = Context()

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
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value)

# transformer within transformer within transformer...

def func3(a, b):

    @transformer
    def func2(a, b):
        @transformer
        def func(a, b):
            import time
            time.sleep(2)
            return 100 * a + b
        func.local = False
        return func(a,b)

    return func2(a, b) + func2(b, a)

ctx.tf.code = func3
ctx.tf.meta = {"local": True}
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

ctx.tf.a = 7
ctx.tf.b = 22
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)
