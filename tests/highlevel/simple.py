from seamless.highlevel import Context

ctx = Context()
ctx.a = 10
print(ctx.a.value)

def double_it(a):
    return 2 * a

ctx.transform = double_it
ctx.transform.a = ctx.a
import sys; sys.exit()
ctx.transform.a = 10
ctx.myresult = ctx.transform
print(ctx._ctx.translated.transform.code.value)
#ctx._ctx.translated.double.inp.handle.a = 20
print(ctx._ctx.translated.transform.inp.handle)
ctx.equilibrate()
print(ctx.myresult.value)
ctx.a = 12
ctx.equilibrate()
print(ctx.myresult.value)
