import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell()
    ctx.cell2 = cell()
    ctx.result = cell()
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    }, with_schema=True)
    ctx.cell1_link = link(ctx.cell1)
    ctx.cell1_link.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = pytransformercell()
    ctx.code.connect(ctx.tf.code)
    ctx.schema = cell("json")
    ctx.schema.connect(ctx.tf.schema)
    ctx.result_link = link(ctx.result)
    ctx.tf.c.connect(ctx.result_link)


from seamless.silk import Silk
dummy = Silk()
def validator(self):
    assert self > 0
dummy.set(1.0)
dummy.add_validator(validator)
ctx.schema.set(dummy.schema.copy())

def run(a,b,c):
    c.set(a+b)

ctx.cell1.set(2)
ctx.cell2.set(3)
ctx.code.set(run)
ctx.equilibrate()
print(ctx.result.value)
ctx.cell2.set(-10)
ctx.equilibrate()

print(ctx.result.value)
print(ctx.status())

shell = ctx.tf.shell()
