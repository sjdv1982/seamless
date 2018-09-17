from seamless.highlevel import Context, mylib

def constructor(ctx, dup):
    for n in range(dup):
        cellname = "dup" + str(n+1)
        setattr(ctx, cellname, ctx.spam.value)
        if n+1 > 2:
            getattr(ctx, cellname).set(n+1)
    return ctx

ctx = Context()
ctx.spam = "spam"
mylib.Test = ctx
mylib.Test.set_constructor(
    constructor=constructor,
    post_constructor=None,
    args=[
      {"name": "dup", "as_cell": False, "auth": True},
    ],
    direct_library_update=False
)
ctx = Context()

ctx.test = mylib.Test(dup=6)
print(ctx.test.spam, ctx.test.spam.value)
print(ctx.test.dup3, ctx.test.dup3.value)
print(ctx.test.dup6, ctx.test.dup6.value)

ctx.test2 = mylib.Test(3)
print(ctx.test2.dup1, ctx.test2.dup1.value)
print(ctx.test2.dup2, ctx.test2.dup2.value)
print(ctx.test2.dup3, ctx.test2.dup3.value)
print(ctx.test2.dup6) #does not exist
