"""
Collatz number computation, showing how to do cyclic graphs in seamless using
 nested asynchronous macros.
Taking a starting value "value", do 3 * value + 1 if value is odd,
  value / 2 if value is even. Stop when 1 has been reached.
Overhead is terrible and space requirements are atrocious, but there could be
 a scenario where this could be useful.
"""

from seamless.core import context, cell, macro
ctx = context(toplevel=True)

def refe_collatz(value):
    if value == 1:
        return [1]
    if value % 2:
        newvalue = value * 3 + 1
    else:
        newvalue = value // 2
    return [value] + refe_collatz(newvalue)

def collatz(ctx, value, macro_code, macro_params):    
    print("COLLATZ", value)
    ctx.series = cell()
    if value == 1:
        ctx.series.set([1])
        return
    if value % 2:
        newvalue = value * 3 + 1
    else:
        newvalue = value // 2
    ###ctx.value = cell("int").set(value)
    ###ctx.newvalue = cell("int").set(newvalue)
    ctx.value = cell().set(value)
    ctx.newvalue = cell().set(newvalue)
    ctx.macro_params = cell().set(macro_params)
    m = ctx.macro = macro(macro_params)
    ctx.newvalue.connect(m.value)
    ctx.macro_code = cell("macro").set(macro_code)
    ctx.macro_code.connect(m.code)
    ctx.macro_code.connect(m.macro_code)
    ctx.macro_params.connect(m.macro_params)
    ctx.tf = transformer({"a": "input", "b": "input", "c": "output"})
    ctx.a = cell()
    ctx.a.connect(ctx.tf.a)
    ctx.b = cell()
    ctx.b.connect(ctx.tf.b)
    m.ctx.series.connect(ctx.a)
    ctx.value.connect(ctx.b)
    ctx.tf.code.set("c = [b] + a")
    ctx.tf.c.connect(ctx.series)
    print("/COLLATZ", value)

ctx.start = cell()

ctx.code = cell("macro").set(collatz)
macro_params = {k: "ref" for k in ("value", "macro_code", "macro_params")}
ctx.macro_params = cell().set(macro_params)
m = ctx.macro = macro(ctx.macro_params.value)
ctx.start.connect(m.value)
ctx.code.connect(m.code)
ctx.code.connect(m.macro_code)
ctx.macro_params.connect(m.macro_params)
ctx.series = cell()
start = 27
###start = 10 #7-level nesting
###start = 12 #10-level nesting
###start = 23 #16-level nesting
###start = 27 #111-level nesting
refe = refe_collatz(start)
ctx.start.set(start)

print("building done")
ctx.equilibrate()
print(ctx.macro.ctx.series.value)
assert ctx.macro.ctx.series.value == refe

start = 32
refe = refe_collatz(start)
print(refe)
ctx.start.set(start)
print("building done, 2nd time")
ctx.equilibrate()    
print(ctx.macro.ctx.series.value)