import seamless
seamless.delegate(False)
from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context,cell, transformer

import os
os.makedirs("/tmp/mount-test/sub", exist_ok=True)

with macro_mode_on():
    ctx = context(toplevel=True)

ctx.cell1 = cell().set(1)
ctx.cell2 = cell().set(2)
result = cell().mount("/tmp/mount-test/myresult", persistent=True)
ctx.result = result
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.cell1.connect(ctx.tf.a)
ctx.cell1.mount("/tmp/mount-test/cell1", persistent=True)
ctx.cell2.connect(ctx.tf.b)
ctx.cell2.mount("/tmp/mount-test/cell2", persistent=True)
ctx.code = cell("transformer").set("c = a + b")
ctx.code.mount("/tmp/mount-test/code.py", persistent=True)
ctx.code.connect(ctx.tf.code)
ctx.tf.c.connect(ctx.result)
ctx.sub = context(toplevel=False)
ctx.sub.mycell = cell("text").set("This is my cell\nend")
ctx.sub.mycell.mount("/tmp/mount-test/sub/mycell", persistent=True)

ctx.compute()
print(ctx.result.value)
ctx.cell1.set(10)
ctx.compute()
print(ctx.result.value)
print(ctx.result.value)
ctx.code.set("c = float(a) + float(b) + 1000")
ctx.compute()
print(ctx.result.value)
print(ctx.status)
