from seamless.highlevel import Context

ctx = Context()
ctx.code = "head -$lines testdata > RESULT"
ctx.code.celltype = "text"
ctx.code.mount("/tmp/test.bash", authority="cell")
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "bash"
ctx.tf.docker_image = "ubuntu"
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"
ctx.tf.lines = 3
ctx.tf.code = ctx.code
ctx.result = ctx.tf
ctx.result.celltype = "text"
ctx.result.mount("/tmp/result", "w")
ctx.translate(force=True)
ctx.compute()
print(ctx.result.value)
print(ctx.tf.exception)
ctx.code = """
python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'
echo 'hello' > test.txt
mkdir RESULT
mv test.npy RESULT
mv test.txt RESULT
chmod -R a+w RESULT
"""
ctx.tf.docker_image = "continuumio/anaconda3"
del ctx.result.mount
ctx.result.celltype = "structured"
ctx.result_npy = ctx.result["test.npy"]
ctx.result_txt = ctx.result["test.txt"]
ctx.compute()
print("")
print(ctx.result.value)
print(ctx.result_npy.value)
print(ctx.result_txt.value)
print(ctx.tf.status)