import seamless
seamless.delegate(False)

from seamless.highlevel import Context, Cell

def func(a,b):
    pass

ctx = Context()
ctx.c = Cell("code")
ctx.c = func
ctx.c2_txt = Cell("text")
ctx.c2 = Cell("code")
ctx.c2 = ctx.c2_txt
ctx.compute()
print(ctx.c.status)
print(ctx.c.value)
print()

ctx.c2_txt = "fun("
ctx.compute()
print(ctx.c2.status)
print(ctx.c2.value)
print()

ctx.c = "fun("
ctx.compute()
print(ctx.c.status)
print(ctx.c.value)
ctx.c = func
ctx.compute()
print()

ctx.c.set_buffer(b"fun2(")
ctx.compute()
print(ctx.c.status)
print(ctx.c.value)

ctx.tf = func
ctx.compute()
print(ctx.tf._get_tf().code.status)
print(ctx.tf.code.value)
print()
ctx.tf.code = "1 = 2"
ctx.compute()
print(ctx.tf._get_tf().code.status)
print(ctx.tf.code.value)

'''
ctx.c = func
ctx.c.mount("/tmp/code.py")
ctx.compute()
'''

ctx.tf = func
ctx.tf.code.mount("/tmp/code.py")
ctx.compute()