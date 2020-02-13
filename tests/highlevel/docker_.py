from seamless.highlevel import Context

ctx = Context()
ctx.code = "head -$lines testdata"
ctx.code.celltype = "text"
ctx.code.mount("/tmp/test.bash")
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "docker"
ctx.tf.docker_image = "ubuntu"
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
print(ctx.tf.exception)