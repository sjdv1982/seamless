import seamless
seamless.database_cache.connect()
seamless.database_sink.connect()

from seamless.imperative import transformer

@transformer
def func(a, b):
    import time
    time.sleep(0.4)
    return 100 * a + b
func.blocking = False

result = func(10,20)
print(result.value)
print()
print()

@transformer
def func2(a, b):
    @transformer
    def func(a, b):
        import time
        time.sleep(0.4)
        return 100 * a + b
    func.blocking = False

    v1 = func(a, b)
    v2 = func(b, a)
    v3 = func(2 * a, 2 * b)
    print("V1", v1.value)
    print("V1 LOGS")
    print(v1.logs)
    print("/V1 LOGS")
    print("V2", v2.value)
    print("V2 LOGS")
    print(v2.logs)
    print("/V2 LOGS")
    print("V3", v3.value)
    print("V3 LOGS")
    print(v3.logs)
    print("/V3 LOGS")
    return v1.value + v2.value + v3.value

result = func2(1,2)
print(result)
print()
print()

func2.blocking = False
result = func2(7,8)
print("LOGS")
print(result.logs)
print("/LOGS")
print(result.value)
print()
print()

from seamless.highlevel import Context
ctx = Context()
ctx.tf = func2
ctx.tf.a = 1
ctx.tf.b = 2
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)
ctx.tf.a = 4
ctx.tf.b = 5
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)