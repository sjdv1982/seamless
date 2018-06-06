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
        buffer = None,
        inchannels = None,
        outchannels = [("a",), ("b",)]
    )
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
        buffer = None,
        inchannels = [("x",), ("y",)],
        outchannels = [("y",)]
    )

    ctx.x = cell()
    ctx.code = pytransformercell().set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.result.connect_inchannel(ctx.tf.c, ("y",))
    ctx.result.connect_inchannel(ctx.x, ("x",))

    ctx.tf2 = transformer({
        "y": "input",
        "z": "output"
    })
    ctx.tf2.code.cell().set("z = y + 1000")
    ctx.z = cell("json")
    ctx.result.connect_outchannel(("y",), ctx.tf2.y)
    ctx.tf2.z.connect(ctx.z)

    #ctx.mount("/tmp/mount-test")

ctx.x.set("x")

inp = ctx.inp.handle
#print(inp["q"])
inp["q"]["r"]["x"] = "test"
inp["a"] = 10
inp["b"] = 20
ctx.equilibrate()
result = ctx.result.handle
result["x"] = 100
ctx.x.set("x")
print(ctx.result.value)

#print(ctx.inp.outchannels[("a",)].status())
print(ctx.tf.status())
print(ctx.tf2.status())
print(ctx.z.value)

inp["b"] = 25
print(inp)
ctx.equilibrate()
print(ctx.z.value)


#shell = ctx.tf.shell()
