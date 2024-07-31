import seamless
seamless.delegate(False)
from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, transformer

import os
os.makedirs("/tmp/mount-test", exist_ok=True)

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(1)
    ctx.cell2 = cell().set(2)
    ctx.result = cell()
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.cell1.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = cell("transformer").set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)    
    ctx.result.mount("/tmp/mount-test/myresult", persistent=True, mode="w")
    ctx.cell1.mount("/tmp/mount-test/cell1", persistent=True)
    ctx.cell2.mount("/tmp/mount-test/cell2", persistent=True)
    ctx.sub = context(toplevel=False)
    ctx.sub.mycell = cell("text").set("This is my cell\nend")

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
