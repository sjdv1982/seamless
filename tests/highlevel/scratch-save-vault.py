import os
import shutil
import seamless
seamless.delegate(False)
from seamless.highlevel import Cell, Context

shutil.rmtree("TEMPVAULT", ignore_errors=True)

ctx = Context()
ctx.a = Cell("int").set(2)
ctx.b = Cell("int").set(3)
ctx.tf = lambda a,b: a+b
ctx.tf.scratch = True
ctx.tf.a = ctx.a
ctx.tf.b = ctx.b
ctx.result = ctx.tf
ctx.result.scratch = True
ctx.compute()
print(ctx.result.value)
print(ctx.result.checksum)
ctx.result2 = Cell("str")
ctx.result2.scratch = True
ctx.result2 = ctx.result
ctx.compute()
print(ctx.result2.value)
print(ctx.result2.checksum)


os.mkdir("TEMPVAULT")
ctx.save_vault("TEMPVAULT")

for dirpath, dirnames, filenames in os.walk("TEMPVAULT"):
    for filename in filenames:
        if filename == ".gitkeep":
            continue
        print(os.path.join(dirpath, filename))

shutil.rmtree("TEMPVAULT", ignore_errors=True)
