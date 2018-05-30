import seamless
from seamless.core.macro import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, StructuredCell
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell("json")
    ctx.cell2 = cell("json").set(2)
    ctx.result = cell("json")
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.a_form = cell("json")
    ctx.a = StructuredCell(
        "a",
        ctx.cell1,
        storage = None,
        form = ctx.a_form,
        schema = None,
        inchannels = None,
        outchannels = [()]
    )
    ctx.a.connect_outchannel((), ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = pytransformercell().set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)


    ctx.mount("/tmp/mount-test")

ctx.equilibrate()
print(ctx.result.value)

a = ctx.a.monitor
a.set_path((), 1)

#shell = ctx.tf.shell()
