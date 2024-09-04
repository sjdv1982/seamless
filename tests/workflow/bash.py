import seamless

seamless.delegate(False)

from seamless.workflow import Context

ctx = Context()
ctx.code = "head -$lines testdata > RESULT"
ctx.code.celltype = "text"
ctx.code.mount("/tmp/test.bash", authority="cell")
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "bash"
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"
ctx.tf.lines = 3
ctx.tf.code = ctx.code
ctx.result = ctx.tf
ctx.result.celltype = "mixed"
ctx.compute()
print(ctx.result.value)
ctx.code = "head -3 testdata > firstdata; mkdir -p RESULT/input; cp firstdata RESULT; cp testdata RESULT/input"
ctx.compute()
print(ctx.result.value)
ctx.code = "python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'; cat test.npy > RESULT"
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.status)

ctx.result.celltype = "structured"
ctx.translate()
ctx.code = """
python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'
echo 'hello' > test.txt
mkdir RESULT
mv test.npy test.txt RESULT
"""
ctx.result_npy = ctx.result["test.npy"]
ctx.result_txt = ctx.result["test.txt"]
ctx.compute()
print("")
print(ctx.result.value)
print(ctx.result_npy.value)
print(ctx.result_txt.value)
print(ctx.tf.status)
