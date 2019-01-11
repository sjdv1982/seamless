import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(1)
    ctx.cell2 = cell().set(2)
    ctx.result = cell()
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.cell1_link = link(ctx.cell1)
    ctx.cell1_link.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = pytransformercell().set("""
import time
time.sleep(3)
c = a + b
""")
    ctx.code.connect(ctx.tf.code)
    ctx.result_link = link(ctx.result)
    ctx.tf.c.connect(ctx.result_link)

def callback():
    print("Equilibration complete")
ctx._get_manager().on_equilibrate(callback)
ctx.cell1.set(10)
for n in range(5):
    ctx.equilibrate(1)
    print(ctx.status(), ctx.result.value)
ctx._get_manager().on_equilibrate(callback)        
ctx.cell1.set(12)
for n in range(5):
    ctx.equilibrate(1)
    print(ctx.status(), ctx.result.value)
