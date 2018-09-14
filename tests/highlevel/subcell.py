from seamless.highlevel import Context
ctx = Context()
ctx.a = {}
ctx.a.b = 12
ctx.tf = lambda x,y: x + y
"""
def add(x,y):
    return x + y
ctx.tf.code = add
"""
###ctx.tf.x = ctx.a.b
ctx.tf.x = 12 ###
print(ctx.tf.x)
###ctx.c = 20
###ctx.tf.y = ctx.c
ctx.tf.y = 20 ###
###ctx.d = ctx.tf
ctx.equilibrate()
#print(ctx.tf._get_tf().status())
#print(ctx.d.value)
print(ctx.tf._get_tf().inp.value)
