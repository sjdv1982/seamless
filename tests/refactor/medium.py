import seamless
from seamless.core.macro import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(1)
    ctx.cell2 = cell().set(2)
    ctx.result = cell("json")
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "f": ("input", "ref", "silk"),
        "c": "output"
    })
    ctx.cell1.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = pytransformercell().set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)
    ctx.f = cell("json").set({"f1": 10, "f2": 20})
    ctx.f.connect(ctx.tf.f)

    ctx.mount("/tmp/mount-test")

ctx.equilibrate()
print(ctx.result.value)
ctx.cell1.set(10)
ctx.equilibrate()
print(ctx.result.value)
ctx.code.set("""
c = a * f.f1 + b * f.f2
""")
ctx.equilibrate()
print(ctx.result.value)
print(ctx.status())
print(ctx.f.value)

shell = ctx.tf.shell()
