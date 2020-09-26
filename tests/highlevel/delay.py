from seamless.highlevel import Context
import asyncio

ctx = Context()

def sleep(t):
    fut = asyncio.ensure_future(asyncio.sleep(t))
    asyncio.get_event_loop().run_until_complete(fut)

def func(a, delay):
    print("FUNC", a, delay)
    import time
    time.sleep(delay)
    return a + 0.1 * delay + 1000

ctx.tf1 = func
ctx.tf1.a = 1
ctx.tf1.delay = 0
ctx.tf1.debug = True
ctx.tf2 = func
ctx.intermediate = ctx.tf1
ctx.tf2.a = ctx.intermediate
ctx.tf2.delay = 0
ctx.tf2.debug = True
ctx.result = ctx.tf2
ctx.compute()
print(ctx.result.value)
ctx.tf2.delay = 2
sleep(0.5)

print("START 1")
ctx.tf1.delay = 5
sleep(0.5)
print(ctx.result.status, ctx.result.value.unsilk) # pending, None
print("START 2")
sleep(2)
print(ctx.result.status, ctx.result.value.unsilk) # pending, None !
ctx.compute()
print(ctx.result.value)