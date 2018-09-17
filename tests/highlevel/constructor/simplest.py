from seamless.highlevel import Context, mylib

ctx = Context()
ctx.spam = "spam"
mylib.Test = ctx
mylib.Test.set_constructor(
    constructor=lambda ctx: ctx,
    post_constructor=None,
    args=[],
    direct_library_update=True
)
ctx = Context()
ctx.test = mylib.Test()
print(ctx.test.spam)
print(ctx.test.spam.value)
