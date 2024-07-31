import sys, os

from seamless.highlevel import Context
import seamless

currdir=os.path.dirname(os.path.abspath(__file__))

if "--delegate" in sys.argv[1:]:
    if seamless.delegate():
        exit(1)
else:
    if "--database" in sys.argv[1:]:
        if seamless.delegate(level=3):
            exit(1)
    else:
        seamless.delegate(False)

ctx = Context()
def func1():
    return 42
ctx.func1 = func1
ctx.compute()
print("#1", ctx.func1.result.value, "exception:", ctx.func1.exception)

seamless.config.block_local()
def func2():
    return 88
ctx.func2 = func2
ctx.compute()
print("#2", ctx.func2.result.value, "exception:", ctx.func2.exception)

def func3():
    return 777
ctx.func3 = func3
ctx.func3.meta = {"local": True}
ctx.compute()
print("#3", ctx.func3.result.value, "exception:", ctx.func3.exception)
