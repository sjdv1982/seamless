import seamless
seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, \
  macro, path

def run_macro(ctx):
    ctx.mycell = cell()

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.macro = macro({})
    ctx.macro.code.cell().set(run_macro)
    ctx.a = cell().set(1)
    p = path(ctx.macro.ctx).mycell
    ctx.a.connect(p)
    ctx.aa = cell()
    p.connect(ctx.aa)

ctx.compute()
print(ctx.macro.ctx.mycell.value)
print(ctx.aa.value)
ctx.a.set(None)
ctx.compute()
print(ctx.macro.ctx.mycell.value)
print(ctx.aa.value)
