from seamless.highlevel import Context
import traceback

ctx = Context()
ctx.code = "head -$lines testdata > RESULT"
ctx.code.celltype = "text"
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "bash"
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"
ctx.tf.testdata.celltype = "text"
ctx.tf.lines = 3
ctx.tf.code = ctx.code
ctx.result = ctx.tf
ctx.result.celltype = "mixed"
ctx.compute()
print(ctx.result.value)

from seamless.metalevel.debugmode import ValidationError
try:
    ctx.tf.debug.enable("light")
except ValidationError as exc:
    traceback.print_exc(limit=0)

ctx.tf.debug.enable("sandbox", sandbox_name="bash-shell")
