# Adapted from /seamless/highlevel/stdlib/switch-select/switch-select.py
import seamless
seamless.delegate(False)

from seamless.workflow import Context, Cell
from seamless import stdlib

ctx = Context()
ctx.include(stdlib.switch)
ctx.include(stdlib.select)
ctx.a = 10.0
ctx.a1 = Cell("float")
ctx.a2 = Cell("float")
ctx.a3 = Cell("float")
ctx.f1 = 2.0
ctx.f2 = 3.0
ctx.f3 = 4.0

def add(a,b):
    return a + b
def sub(a,b):
    return a - b
def mul(a,b):
    return a * b

ctx.op1 = add
ctx.op1.a = ctx.a1
ctx.op1.b = ctx.f1
ctx.r1 = ctx.op1

ctx.op2 = sub
ctx.op2.a = ctx.a2
ctx.op2.b = ctx.f2
ctx.r2 = ctx.op2

ctx.op3 = mul
ctx.op3.a = ctx.a3
ctx.op3.b = ctx.f3
ctx.r3 = ctx.op3

adict = {
    "path1": ctx.a1,
    "path2": ctx.a2,
    "path3": ctx.a3,
}
rdict = {
    "path1": ctx.r1,
    "path2": ctx.r2,
    "path3": ctx.r3,
}
ctx.selected = "path1"

ctx.switch = ctx.lib.switch(
    celltype="float",
    input=ctx.a,
    selected=ctx.selected,
    outputs=adict,
)
ctx.compute()
ctx.output = Cell("float")
"""
ctx.select = ctx.lib.select(
    celltype="float",
    inputs=rdict,
    selected=ctx.selected,
    output=ctx.output,
)
"""
# Alternative syntax
ctx.select = ctx.lib.select()
ctx.select.celltype = "float"
ctx.select.inputs = rdict
ctx.select.selected = ctx.selected
ctx.output = ctx.select.output
# /
ctx.compute()

print(ctx.output.value)
print(ctx.a.value, ctx.a1.value, ctx.a2.value, ctx.a3.value)
print(ctx.a1.status, ctx.a2.status, ctx.a3.status)
print(ctx.r1.value, ctx.r2.value, ctx.r3.value)
print()

ctx.selected = "path2"
print(ctx._needs_translation)
ctx.compute()
print(ctx.output.value)
print(ctx.a.value, ctx.a1.value, ctx.a2.value, ctx.a3.value)
print(ctx.a1.status, ctx.a2.status, ctx.a3.status)
print(ctx.r1.value, ctx.r2.value, ctx.r3.value)
print()

ctx.selected = "path3"
print(ctx._needs_translation)
ctx.compute()
print(ctx.output.value)
print(ctx.a.value, ctx.a1.value, ctx.a2.value, ctx.a3.value)
print(ctx.a1.status, ctx.a2.status, ctx.a3.status)
print(ctx.r1.value, ctx.r2.value, ctx.r3.value)
print()

graph = ctx.get_graph()
ctx.save_graph("switch-select-stdlib.seamless")
ctx.save_zip("switch-select-stdlib.zip")