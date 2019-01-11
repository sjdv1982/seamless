from seamless.highlevel import Context

ctx = Context()
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "bash"
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"    
ctx.tf.lines = 3
ctx.tf.code = "head -$lines testdata"
ctx.result = ctx.tf
ctx.equilibrate()
print(ctx.result.value)
ctx.tf.code = "tar czf test.tgz testdata; cat test.tgz"
ctx.equilibrate()
print(ctx.result.value)
ctx.tf.code = "python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'; cat test.npy"
ctx.equilibrate()
print(ctx.result.value)
