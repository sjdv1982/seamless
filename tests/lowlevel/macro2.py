import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pymacrocell, macro

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell("plain").set(1)

    ctx.mymacro = macro({
        "param": "copy",
    })

    ctx.param.connect(ctx.mymacro.param)
    ctx.inp = cell("text").set("INPUT")
    ctx.mymacro_code = pymacrocell().set("""
print("Executing 'mymacro'...")
ctx.submacro = macro({
    "inp": "copy"
})
ctx.submacro_code = pymacrocell().set('''
print("Executing 'submacro, param = %s'...")
ctx.myinp = cell("text").set(inp + "!!!")
''' % param)
ctx.submacro_code.connect(ctx.submacro.code)
ctx.inp2 = cell("text")
ctx.inp2.connect(ctx.submacro.inp)
""")
    ctx.mymacro_code.connect(ctx.mymacro.code)
    ctx.inp.connect(ctx.mymacro.ctx.inp2)

print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
ctx.mymacro.ctx.submacro.ctx.myinp.set(10)
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
print("*" * 60)
print("Stage 1")
print("*" * 60)
ctx.inp.set("INP")
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
ctx.mymacro.ctx.submacro.ctx.myinp.set(20)
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
print("*" * 60)
print("Stage 2")
print("*" * 60)
ctx.param.set(2)
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
print("*" * 60)
print("Stage 3")
print("*" * 60)
ctx.inp.set("INP2")
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
