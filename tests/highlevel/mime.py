from seamless.highlevel import Context, Reactor
ctx = Context()
ctx.test = "<b>This is a test</b>"
print("cell:")
print(ctx.test.mimetype)
ctx.test.datatype = "text"
print(ctx.test.mimetype)
ctx.test.datatype = "html"
print(ctx.test.mimetype)
ctx.test.mimetype = "text/xhtml"
print(ctx.test.mimetype)
print()

ctx.tf = lambda a,b: 10
print("transformer:")
print(ctx.tf.code.mimetype)
print()

ctx.rc = Reactor()
print("reactor:")
print(ctx.rc.code_start.mimetype)
print(ctx.rc.code_update.mimetype)
print(ctx.rc.code_stop.mimetype)
print()

ctx.tf._get_htf()["language"] = "cpp" #hack
print("C++ transformer:")
print(ctx.tf.code.mimetype)
