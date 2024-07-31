import seamless
seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, transformer, macro

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell("plain").set(1)

    ctx.mymacro = macro({
        "param": "plain",
    })

    ctx.param.connect(ctx.mymacro.param)
    ctx.inp = cell("text").set("INPUT")
    ctx.mymacro_code = cell("macro").set("""
print("Executing 'mymacro'...")
ctx.submacro = macro({
    "inp": "plain"
})
ctx.submacro_code = cell("macro").set('''
print("Executing 'submacro, param = %s'...")
ctx.myinp = cell("text").set(inp + "!!!")
''' % param)
ctx.submacro_code.connect(ctx.submacro.code)
ctx.inp2 = cell("text")
ctx.inp2.connect(ctx.submacro.inp)
""")
    ctx.mymacro_code.connect(ctx.mymacro.code)
    ctx.inp.connect(ctx.mymacro.ctx.inp2)

ctx.compute()
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
ctx.mymacro.ctx.submacro.ctx.myinp.set(10)
ctx.compute()
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
print("*" * 60)
print("Stage 1")
print("*" * 60)
ctx.inp.set("INP")
ctx.compute()
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
ctx.mymacro.ctx.submacro.ctx.myinp.set(20)
ctx.compute()
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
print("*" * 60)
print("Stage 2")
print("*" * 60)
ctx.param.set(2)
ctx.compute()
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
print("*" * 60)
print("Stage 3")
print("*" * 60)
ctx.inp.set("INP2")
ctx.compute()
print(ctx.mymacro.ctx.submacro.ctx.myinp.value)
