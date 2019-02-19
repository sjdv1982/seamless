import seamless
from seamless.core import macro_mode_on
from seamless.core import context,textcell, cell, transformer, pytransformercell

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.mount("/tmp/mount-test", persistent=None)

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
ctx.cell2.connect(ctx.tf.b)
ctx.code = pytransformercell().set("c = a + b")
ctx.code.connect(ctx.tf.code)
ctx.tf.c.connect(ctx.result)
ctx.sub = context(toplevel=False)
ctx.sub.mycell = textcell().set("This is my cell\nend")

ctx.equilibrate()
print(ctx.result.value)
ctx.cell1.set(10)
ctx.equilibrate()
print(ctx.result.value)
print(ctx.result.value)
ctx.code.set("c = float(a) + float(b) + 1000")
ctx.equilibrate()
print(ctx.result.value)
print(ctx.status)
