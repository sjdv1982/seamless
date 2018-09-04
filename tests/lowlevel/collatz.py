"""
Collatz number computation, showing how to do cyclic graphs in seamless using
 nested asynchronous macros.
Taking a starting value "value", do 3 * value + 1 if value is odd,
  value / 2 if value is even. Stop when 1 has been reached.
Overhead is terrible and space requirements are atrocious, but there could be
 a scenario where this could be useful.
"""

import sys
sys.USE_TRANSFORMER_CODE = True #kludge to share a variable without an extra slowdown

from seamless.core import context, cell, macro
ctx = context(toplevel=True)

def collatz(ctx, value, macro_code, macro_params):
  import sys #kludge
  print("COLLATZ", value)
  ctx.series = cell("json")
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
  ctx.macro_params = cell("json").set(macro_params)
  m = ctx.macro = macro(ctx.macro_params.value)
  ctx.newvalue.connect(m.value)
  ctx.macro_code = cell("macro").set(macro_code)
  ctx.macro_code.connect(m.code)
  ctx.macro_code.connect(m.macro_code)
  ctx.macro_params.connect(m.macro_params)
  if sys.USE_TRANSFORMER_CODE: ###transformer code version
      ctx.tf = transformer({"a": "input", "b": "input", "c": "output"})
      m.gen_context.series.connect(ctx.tf.a)
      ctx.value.connect(ctx.tf.b)
      ctx.tf.code.set("c = [b] + a")
      ctx.tf.c.connect(ctx.series)
      print("/COLLATZ", value)
  else: #no transformer code, exploits that macro is synchronous
      series = [value] + m.gen_context.series.value
      ctx.series.set(series)
      print("/COLLATZ", series)

ctx.start = cell()

ctx.code = cell("macro").set(collatz)
macro_params = {k: "ref" for k in ("value", "macro_code", "macro_params")}
ctx.macro_params = cell("json").set(macro_params)
m = ctx.macro = macro(ctx.macro_params.value)
ctx.start.connect(m.value)
ctx.code.connect(m.code)
ctx.code.connect(m.macro_code)
ctx.macro_params.connect(m.macro_params)
ctx.series = cell("json")
ctx.start.set(10) #7-level nesting here works well for tf and non-tf code
###ctx.start.set(12) #10-level nesting works with non-tf,  but equilibrate for tf is getting very slow
###ctx.start.set(23) #16-level nesting here works well non-tf code (equilibrate too slow for tf)
###ctx.start.set(27) #111-level nesting
# - equilibrate() does not work well with transformer code
# - activate() is too slow, even for non-transformer code

print("building done")
ctx.equilibrate() #only needed for tf code
print(ctx.macro.gen_context.series.value)

import sys; sys.exit()
ctx.start.set(32)
print("building done, 2nd time")
ctx.equilibrate() #only needed for tf code, but doesn't work if previously too deeply nested (bug in equilibrate?)
print(ctx.macro.gen_context.series.value)
