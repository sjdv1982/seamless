import seamless

seamless.delegate(False)

from seamless.workflow import Context, Transformer

ctx = Context()

ctx.tf = Transformer()
ctx.tf.language = "bash"
ctx.tf.code = "head -$lines sub/testdata > RESULT"
ctx.tf["sub/testdata"] = "a \nb \nc \nd \ne \nf \n"
ctx.tf.lines = 3
ctx.compute()
print(ctx.tf.logs)

del ctx.tf
ctx.translate()

ctx.tf = Transformer()
ctx.tf.language = "bash"
ctx.tf.code = "head -$lines sub/../../testdata > RESULT"
ctx.tf["sub/../../testdata"] = "a \nb \nc \nd \ne \nf \n"
ctx.tf.lines = 3
ctx.compute()
print(ctx.tf.logs)
