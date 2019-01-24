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
    ctx.code = pytransformercell().set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.result_link = link(ctx.result)
    ctx.tf.c.connect(ctx.result_link)

print(ctx.cell1.value)
print(ctx.code.value)
ctx.equilibrate()
print(ctx.result.value, ctx.status)
ctx.cell1.set(10)
ctx.equilibrate()
print(ctx.result.value, ctx.status)
ctx.code.set("c = a + b + 1000")
ctx.equilibrate()
print(ctx.result.value, ctx.status)

print("Introduce delay...")
ctx.code.set("import time; time.sleep(2); c = -(a + b)")
ctx.equilibrate(1.0)
print("after 1.0 sec...")
print(ctx.result.value, ctx.status)
print("...")
ctx.equilibrate()
print(ctx.result.value, ctx.status)
