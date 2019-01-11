from seamless.highlevel import Context

ctx = Context()
#ctx.mount("/tmp/mount-test")

ctx.a = 12

def func(a, b):
    return [bb + 3 * a for bb in b]

ctx.transform = func
ctx.transform.b = [100,200,300]
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
ctx.equilibrate()
print(ctx.myresult.value)
