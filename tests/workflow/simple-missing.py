import seamless
seamless.delegate(False)

from seamless.workflow import Context

ctx = Context()
def func(a,b,c):
    return 42

ctx.tf = func
ctx.tf.a = 10
ctx.tf.b = 20
ctx.result = ctx.tf

print("START")
ctx.compute()
print(ctx.status)
print(ctx.tf._get_tf().inp.status) #TODO: nicer API/messages