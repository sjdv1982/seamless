from seamless.highlevel import Context
ctx = Context()
def func():
    import time
    time.sleep(2)
    return 42
ctx.tf = func
ctx.result = ctx.tf.result
ctx.result.celltype = "text"
ctx.result.mount("mount-write.txt", "w")
ctx.translate()
ctx.compute()
import os
assert os.path.exists("mount-write.txt")
with open("mount-write.txt") as f:
    assert f.read() == "42\n"
del ctx
os.remove("mount-write.txt")