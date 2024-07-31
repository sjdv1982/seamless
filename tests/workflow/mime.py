import seamless
seamless.delegate(False)

from seamless.highlevel import Context
ctx = Context()
ctx.test = "<b>This is a test</b>"
print("cell:")
print(ctx.test.mimetype)
ctx.test.mimetype = "text/plain"
print(ctx.test.mimetype)
del ctx.test.mimetype
ctx.test.datatype = "html"
print(ctx.test.mimetype)
ctx.test.mimetype = "text/xhtml"
print(ctx.test.mimetype)
print()

ctx.tf = lambda a,b: 10
print("transformer:")
print(ctx.tf.code.mimetype)
print()

ctx.tf.language = "cpp"
print("C++ transformer:")
print(ctx.tf.code.mimetype)
