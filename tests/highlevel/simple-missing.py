from seamless.highlevel import Context

ctx = Context()
def func(a,b,c):
    return 42

ctx.tf = func
ctx.tf.a = 10
ctx.tf.b = 20
ctx.result = ctx.tf

print("START")
ctx.equilibrate()
print(ctx.status)
print(ctx.tf._get_tf().inp.status) #TODO: nicer API/messages