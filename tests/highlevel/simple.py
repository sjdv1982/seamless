from seamless.highlevel import Context

ctx = Context()
ctx.a = 10
print(ctx.a.value)

def double(a):
    return 2 * a

ctx.transform = double
#ctx.transform.a = ctx.a
ctx.transform.a = 10
ctx.result = ctx.transform 
print(ctx._ctx.translated.transform.code.value)
#ctx._ctx.translated.double.inp.handle.a = 20
print(ctx._ctx.translated.transform.inp.handle)
