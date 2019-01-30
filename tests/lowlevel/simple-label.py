import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell()
    ctx.cell2 = cell()

ctx.cell1.set(5)
ctx.cell1.set_label("five")
print(ctx.cell1.label)
print(ctx.cell1.value)
ctx.cell1.set(7)

ctx.cell2.from_label("five")
print(ctx.cell2.label)
print(ctx.cell2.value)

print(ctx.cell1.label)
print(ctx.cell1.value)