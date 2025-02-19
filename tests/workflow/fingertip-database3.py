from seamless.workflow import Context, Cell
from seamless import Checksum
import seamless

seamless.delegate(3, raise_exceptions=True)
ctx = Context()


def mul(a, b):
    return a * b


ctx.mul = mul
ctx.intermediate = Cell()
ctx.intermediate.celltype = "float"
ctx.intermediate.scratch = True
ctx.translate()
ctx.intermediate.checksum = Checksum(
    "39dacbda510b82b6fec0680fb7beb110eef660f5daef6c129ef1abfde1d4d331"
)
ctx.mul.a = ctx.intermediate
ctx.mul.b = 3
ctx.compute()
print(ctx.mul.result.value)
print(
    ctx.mul.exception,
    ctx.mul.exception is not None and ctx.mul.exception.startswith("CacheMissError"),
)
ctx.intermediate.checksum.resolve()
print(ctx.intermediate.value)
ctx.mul.clear_exception()
ctx.compute()
print(ctx.mul.result.value)
print(ctx.mul.exception)
