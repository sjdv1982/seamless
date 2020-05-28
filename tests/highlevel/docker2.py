from seamless.highlevel import Context

ctx = Context()
ctx.code = "head -$lines testdata"
ctx.code.celltype = "text"
ctx.code.mount("/tmp/test.bash")
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "docker"
ctx.tf.docker_image = "rpbs/seamless"
ctx.tf.docker_options = {"name": "ubuntu-container"}
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"
ctx.tf.lines = 3
ctx.tf.code = ctx.code
ctx.result = ctx.tf
ctx.result.celltype = "text"
ctx.result.mount("/tmp/result", "w")
ctx.translate(force=True)
ctx.compute()
print(ctx.result.value)
ctx.code = "head -3 testdata > firstdata; tar czf test.tgz testdata firstdata; cat test.tgz"
ctx.compute()
print(ctx.result.value)
ctx.code = "python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'; cat test.npy"
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.status)
print(ctx.tf.exception)
ctx.code = "python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'; echo OK > ok; tar czf test.tgz ok test.npy; cat test.tgz"
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.status)
print(ctx.tf.exception)