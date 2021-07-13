from seamless.highlevel import Context
def func(a):
    return a+100
ctx = Context()
ctx.func = func
ctx.func.a = 12
ctx.func.environment.set_image({"name": "nonsense"})
env = ctx.func.environment
ctx.compute()
print(ctx.func.exception)
ctx.func.environment.set_image({"name": "rpbs/seamless"})
ctx.compute()
print(ctx.func.status)
print(ctx.func.result.value)
