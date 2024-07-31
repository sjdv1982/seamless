import seamless
seamless.delegate(False)

from seamless.workflow import Context, Transformer

tf = Transformer()
tf.language = "bash"
tf.code = "head -$lines testdata > RESULT"
tf.testdata = "a \nb \nc \nd \ne \nf \n"
tf.lines = 3

ctx = Context()
ctx.tf = tf.copy()
ctx.result = ctx.tf
ctx.result.celltype = "mixed"
ctx.compute()
print(ctx.result.value)
ctx.tf.lines = 4
ctx.compute()
print(ctx.result.value)

tf.lines = 2
ctx.compute()
print(ctx.result.value)
ctx.tf = tf.copy()
ctx.result = ctx.tf
ctx.result.celltype = "mixed"
ctx.compute()
print(ctx.result.value)

#tr = tf.run()
#print(tr.value)