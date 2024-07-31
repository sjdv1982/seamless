from seamless.highlevel import Context, Transformer

import seamless.core.execute
seamless.core.execute.DIRECT_PRINT = True

ctx = Context()
def func():
    print("START")
    import time
    time.sleep(1000)
    return 42
ctx.tf = func
ctx.translate()
print("now type ctx.compute()")