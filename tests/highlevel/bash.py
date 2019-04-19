from seamless.highlevel import Context

ctx = Context()
ctx.code = "head -$lines testdata"
ctx.code.celltype = "text"
ctx.code.mount("/tmp/test.bash")
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "bash"
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"    
ctx.tf.lines = 3
ctx.tf.code = ctx.code
ctx.result = ctx.tf
ctx.result.mount("/tmp/result")
ctx.translate(force=True)
ctx.equilibrate()
print(ctx.result.value)
ctx.code = "tar czf test.tgz testdata; cat test.tgz"
ctx.equilibrate()
print(ctx.result.value)
ctx.code = "python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'; cat test.npy"
ctx.equilibrate()
print(ctx.result.value)