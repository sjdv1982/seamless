import seamless

seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, transformer

with macro_mode_on():
    topctx = context(toplevel=True)
    ctx = topctx.sub = context(toplevel=False)
    assert topctx.sub is ctx
    ctx.cell1 = cell().set(1)
    ctx.cell2 = cell().set(2)
    ctx.result = cell()
    ctx.tf = transformer({"a": "input", "b": "input", "c": "output"})
    ctx.cell1.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = cell("transformer").set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)

topctx.compute()
print(ctx.result.value)
ctx.cell1.set(10)
topctx.compute()
print(ctx.result.value)
ctx.code.set("c = a + b + 1000")
topctx.compute()
print(ctx.result.value)
print(ctx.status)
