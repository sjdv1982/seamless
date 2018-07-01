import seamless
from seamless.core import macro_mode_on
from seamless.core import context,textcell, transformer, pytransformercell

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = textcell().set(1)
    ctx.cell2 = textcell().set(2)
    ctx.result = textcell()
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.cell1.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = pytransformercell().set("c = float(a) + float(b)")
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)
    ctx.result.mount("/tmp/mount-test/myresult", persistent=True)
    ctx.mount("/tmp/mount-test")
    ctx.sub = context(toplevel=False, context=ctx, name="sub")
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
print(ctx.status())
