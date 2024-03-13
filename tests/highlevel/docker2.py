import seamless
seamless.delegate(False)

from seamless.highlevel import Context

ctx = Context()
ctx.code = "head -$lines testdata > RESULT"
ctx.code.celltype = "text"
ctx.code.mount("/tmp/test.bash", authority="cell")
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "bash"
ctx.tf.docker_image = "rpbs/seamless"
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"
ctx.tf.lines = 3
ctx.tf.code = ctx.code
ctx.result = ctx.tf
ctx.result.celltype = "text"
ctx.result.mount("/tmp/result", "w")
ctx.translate(force=True)
ctx.compute()
print(ctx.result.value)
ctx.code = "head -3 testdata > firstdata; mkdir RESULT; mv testdata firstdata RESULT"
ctx.compute()
print(ctx.result.value)
ctx.code = "python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'; cat test.npy > RESULT"
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.status)
print(ctx.tf.exception)
ctx.code = "python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'; echo OK > ok; mkdir RESULT; mv ok test.npy RESULT"
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.status)
print(ctx.tf.exception)