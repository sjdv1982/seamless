from seamless.highlevel import Context, Transformer, Cell

ctx = Context()
ctx.r_code = Cell("code").mount("example.R")
ctx.r_code.language = "r"
ctx.compute()

ctx.tf = Transformer()
ctx.tf.a = 22
ctx.tf.b = 7
ctx.tf.language = "r"
ctx.tf.code = ctx.r_code

ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value)

ctx.r_code.mount("plot.R", authority="file")
ctx.result = ctx.tf.result
ctx.result.celltype = "text"
ctx.result.mimetype = "svg"
ctx.result.share("result.svg")
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.result.checksum is not None)
print(ctx.result.status)

ctx.result2 = ctx.tf.result
ctx.result2.celltype = "bytes"
ctx.result2.mimetype = "png"
ctx.result2.share("result.png")

par = ctx.environment.get_py_bridge("r")[1]
par["device"] = "png"
ctx.environment.set_py_bridge_parameters("r", par)
ctx.compute()

print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.result2.checksum is not None)
print(ctx.result2.status)
