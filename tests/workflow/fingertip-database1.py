from seamless.workflow import Context
import seamless

seamless.delegate(3, raise_exceptions=True)
ctx = Context()


def double(a):
    return 2 * a


ctx.a = 2
ctx.double = double
ctx.double.a = ctx.a
ctx.double.scratch = True
ctx.double.result.celltype = "float"
ctx.intermediate = ctx.double.result
ctx.intermediate.celltype = "float"
ctx.intermediate.scratch = True
ctx.compute()
print(ctx.intermediate.value)
print(ctx.intermediate.checksum)
