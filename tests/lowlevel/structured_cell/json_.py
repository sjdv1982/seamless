import seamless
from seamless.core.macro import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, StructuredCell
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.inp_struc = context(name="inp_struc",context=ctx)
    ctx.inp_struc.data = cell("json")
    ctx.inp_struc.form = cell("json")
    ctx.inp = StructuredCell(
        "inp",
        ctx.inp_struc.data,
        storage = None,
        form = ctx.inp_struc.form,
        schema = None,
        inchannels = None,
        outchannels = [("a",), ("b",)]
    )
    ctx.inp.monitor.set_path((), {"a": 10})
    ctx.inp.connect_outchannel(("a",), ctx.tf.a)
    ctx.inp.connect_outchannel(("b",), ctx.tf.b)

    ctx.result_struc = context(name="result_struc",context=ctx)
    ctx.result_struc.data = cell("json")
    ctx.result_struc.form = cell("json")
    ctx.result = StructuredCell(
        "result",
        ctx.result_struc.data,
        storage = None,
        form = ctx.result_struc.form,
        schema = None,
        inchannels = [("x",), ("y",)],
        outchannels = [("y",)]
    )

    ctx.x = cell()
    ctx.code = pytransformercell().set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.result.connect_inchannel(ctx.tf.c, ("y",))
    ###ctx.result.connect_inchannel(ctx.x, ("x",)) #TODO: cell-cell

    ctx.tf2 = transformer({
        "y": "input",
        "z": "output"
    })
    ctx.tf2.code.cell().set("z = y + 1000")
    ctx.z = cell("json")
    ctx.result.connect_outchannel(("y",), ctx.tf2.y)
    ctx.tf2.z.connect(ctx.z)

    #ctx.mount("/tmp/mount-test")

ctx.inp.monitor.set_path(("b",), 20)
ctx.equilibrate()
print(ctx.result.value)

#print(ctx.inp.outchannels[("a",)].status())
print(ctx.tf.status())
print(ctx.tf2.status())
print(ctx.z.value)

ctx.inp.monitor.set_path(("b",), 25)
ctx.equilibrate()
print(ctx.z.value)

#shell = ctx.tf.shell()
