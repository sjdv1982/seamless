from seamless.highlevel import Context

code = """
sleep 3
head -$lines testdata > RESULT
"""

ctx = Context()
ctx.code = code
ctx.code.celltype = "text"
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "bash"
ctx.tf.docker_image = "ubuntu"
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"
ctx.tf.lines = 3
ctx.tf.code = ctx.code

ctx.compute(1)
ctx.tf.lines = 2  # This will cancel the old transformer, and hopefully the Docker image
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value)