from seamless.workflow import Context, Cell
from seamless import Checksum
import seamless

seamless.delegate(1, force_database=True, raise_exceptions=True)
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
ctx.result = ctx.mul
ctx.compute()
print(ctx.mul.result.checksum)
try:
    print(ctx.mul.result.value)
except seamless.CacheMissError:
    print("cache miss, as expected")


# note: observe the difference with fingertip-database4
# Direct resolution does not work with delegate=3
#  => the intermediate value gets fingertipped but never stored
ctx.intermediate.checksum.resolve()  # extra line
#
ctx.mul.result.checksum.resolve()
print(ctx.mul.result.value)
