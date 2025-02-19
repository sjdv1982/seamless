from seamless.workflow import Context, Cell
from seamless import Checksum
import seamless

seamless.delegate(1, force_database=True, raise_exceptions=True)
ctx = Context()

ctx.intermediate = Cell()
ctx.intermediate.celltype = "float"
ctx.intermediate.scratch = True
ctx.translate()
ctx.intermediate.checksum = Checksum(
    "39dacbda510b82b6fec0680fb7beb110eef660f5daef6c129ef1abfde1d4d331"
)
print(ctx.intermediate.value)
