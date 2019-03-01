import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, StructuredCell
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.inp_struc = context(toplevel=False)
    ctx.inp_struc.data = cell("mixed")
    ctx.inp = StructuredCell(
        "inp",
        ctx.inp_struc.data,
        schema = None,
        buffer = None,
        plain = True,
        inchannels = None,
        outchannels = [("a",), ("b",)]
    )
    ctx.inp.outchannels[("a",)].connect(ctx.tf.a)
    ctx.inp.outchannels[("b",)].connect(ctx.tf.b)

    ctx.result_struc = context(toplevel=False)
    ctx.result_struc.data = cell("mixed")
    ctx.result = StructuredCell(
        "result",
        ctx.result_struc.data,
        schema = None,
        buffer = None,
        plain = True,
        inchannels = [("x",), ("y",)],
        outchannels = [("y",)]
    )

    ctx.x = cell()
    ctx.code = pytransformercell().set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.x.connect(ctx.result.inchannels[("x",)])
    ctx.tf.c.connect(ctx.result.inchannels[("y",)])

    ctx.tf2 = transformer({
        "y": "input",
        "z": "output"
    })
    ctx.tf2.code.cell().set("z = y + 1000")
    ctx.z = cell("mixed")
    ctx.result.outchannels[("y",)].connect(ctx.tf2.y)
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
print(ctx.tf.status)
print(ctx.tf2.status)
print(ctx.z.value)

inp["b"] = 25
print(inp)
ctx.equilibrate()
print(ctx.z.value)


#shell = ctx.tf.shell()
