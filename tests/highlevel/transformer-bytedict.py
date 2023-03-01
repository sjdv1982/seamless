from seamless.highlevel import Context

def func():
    import numpy as np
    result = {}
    result["a"] = b'abc'
    result["a2"] = 'xyz'
    result["b"] = np.arange(3).tobytes()
    result["c"] = 42
    return result

ctx = Context()
ctx.tf = func
ctx.result = ctx.tf
ctx.compute()
print(ctx.tf.result.value)
print()
print(ctx.result.value)
print()
ctx.a = ctx.result.a
ctx.compute()
print(ctx.a.value)
print()
ctx.a.celltype = "binary"
ctx.compute()
print(ctx.a.value, type(ctx.a.value), ctx.a.celltype)
print()
ctx.a.celltype = "bytes"
ctx.compute()
print(ctx.a.value, type(ctx.a.value), ctx.a.celltype)
print()
ctx.aa = ctx.a
ctx.aa.celltype = "text"
ctx.compute()
print(ctx.aa.value, type(ctx.aa.value), ctx.aa.celltype)
print()
ctx.a2 = ctx.result.a2
ctx.a2.celltype = "text"
ctx.compute()
print(ctx.a2.value, type(ctx.a2.value), ctx.a2.celltype)
