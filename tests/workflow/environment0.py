import seamless
seamless.delegate(False)

from seamless.workflow import Context
def func(a):
    return a+100
ctx = Context()
ctx.func = func
ctx.func.a = 12
ctx.func.environment.set_docker({"name": "nonsense"})
env = ctx.func.environment
ctx.compute()
print(ctx.func.exception)
ctx.func.environment.set_docker({"name": "rpbs/seamless"})
ctx.translate()
ctx.func.clear_exception()
ctx.compute()
print(ctx.func.status)
print(ctx.func.result.value)