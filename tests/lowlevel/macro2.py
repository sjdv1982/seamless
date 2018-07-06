import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, macro

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell("json").set(1)

    ctx.macro = macro({
        "param": "copy",
    })

    ctx.param.connect(ctx.macro.param)
    ctx.inp = cell("text").set("INPUT")
    ctx.macro_code = pytransformercell().set("""
print("Execute macro")
ctx.submacro = macro({
    "inp": "copy"
})
ctx.submacro_code = pytransformercell().set('''
print("Execute submacro")
ctx.inp = cell("text").set(inp + "!!!")
''')
ctx.submacro_code.connect(ctx.submacro.code)
    """)
    ctx.macro_code.connect(ctx.macro.code)
    ctx.inp.connect(ctx.macro.ctx.submacro.inp)

print(ctx.macro.ctx.submacro.ctx.inp.value)
ctx.macro.ctx.submacro.ctx.inp.set(10)
print(ctx.macro.ctx.submacro.ctx.inp.value)
print("Stage 1")
ctx.inp.set("INP")
print(ctx.macro.ctx.submacro.ctx.inp.value)
ctx.macro.ctx.submacro.ctx.inp.set(20)
print(ctx.macro.ctx.submacro.ctx.inp.value)
print("Stage 2")
ctx.param.set(2)
print("Stage 3")
ctx.inp.set("INP2")
print(ctx.macro.ctx.submacro.ctx.inp.value)
