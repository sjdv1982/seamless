from seamless.highlevel import Context
import inspect
def help(obj):
    print("*" * 80)
    print(inspect.getdoc(obj))
    print("*" * 80)
    print()

help(Context)
ctx = Context()
help(ctx)
ctx.help = "This is a help string"
help(ctx)
print(ctx.help.value)
ctx.help.share("help/index.txt")
ctx.translate()
ctx.help = "Updated help string"
ctx.compute()
print(ctx.help.value)

ctx.create_help("context")
print(ctx.help)
print(ctx.help.index.value)