from seamless import context
import seamless.lib

ctx = context()
c, p = ctx.cells, ctx.processes #p contains both processes and subcontexts


p.add = seamless.lib.examples.add() #or: p.add(seamless.lib.examples.add())
print(p.add.keys()) #["input1", "input2", "output"]
print(p.add.pins())
"""
{
  "input1": {
    "type": "inputpin",
    ...
  },
  ...
}
"""
p.add.input1.cell().set(2)
#process.outputpin.cell() creates a cell if it does not exist yet; name is cell1
p.add.input2.cell().set(3)  #creates cell2
outp = p.add.output.cell() #creates cell3
print(outp) #5
print(c.cell1) #2
print(c.cell2) #3
print(c.cell3) #5
print(c.cell3 is outp) #True
p.mult = seamless.lib.examples.mult(c.cell2, c.cell3)
outp = p.mult.output.cell()
print(outp) #15
print(c.keys()) #["cell1", "cell2", "cell3", "cell4"]
print(outp is c.cell4) #True
print(isinstance(c.mult), context) #True
print(p.add.collapse()) #collapses the subcontext into the parent context
"""
{
  "processes": ["add1"],
  "cells" : ["pythoncell_add1"]
}
"""
#p.add no longer exists, but c.add1 and c.pythoncell_add1 do

print(p.mult.collapse())
"""
{
  "processes": ["mult1"],
  "cells" : ["pythoncell_mult1"]
}
"""
print(c.keys()) #["cell1", "cell2", "cell3", "cell4", "pythoncell_add1", "pythoncell_mult1"]
print(p.mult1.keys()) ["input1", "input2", "code", "output"]
outp = p.mult1.output.cell()
p.mult1.code.disconnect()
c.purge() #removes c.pythoncell_mult1
c.pythoncell_add1.connect(p.mult1.code)
print(outp) #8
c.mycell(("source", "python")).set("return input1 + 2 * input2")
#or:
#c.python.mycell("return input1 + 2 * input2")
#or:
#c.mycell = pythoncell("return input1 + 2 * input2")
p.mult1.code.disconnect()
c.mycell.connect(p.mult1.code)
print(outp) #13


#macro code: lib/examples.py

from seamless import macro

@macro
def add(ctx):
  c, p = ctx.cells, ctx.processes
  from seamless import transformer
  transformer_params = {
    "code" : {
      "pin": "inputpin",
      "type" : "codeblock",
    },
    "input" : {
      "pin": "inputpin",
    },
    "output" : {
      "pin": "outputpin",
    }
  }
  t = transformer(transformer_params)
  p.define(t) #p.add1 = transformer(...)
  t.code.cell().set("return input + output") #defines not c.pythoncell1 but c.pythoncell_add1
  ctx.define_pins(t)
  #defines ctx.pins.input and ctx.pins.output because they are unconnected
  #to do it manually: ctx.pins.input = seamless.core.inputpin(t.input)

#alternative implementation
@macro
def add(ctx):
  c, p = ctx.cells, ctx.processes
  from seamless.lib.basic import simple_transformer
  t = simple_transformer(["input"], ["output"])
  p.define(t)
  t.code.cell().set("return input + output") #defines not c.pythoncell1 but c.pythoncell_add1
  ctx.define_pins(t)

@macro
def mult(ctx):
  c, p = ctx.cells, ctx.processes
  from seamless.lib.basic import simple_transformer
  t = simple_transformer(["input"], ["output"])
  p.define(t)
  t.code.cell().set("return input * output") #defines not c.pythoncell1 but c.pythoncell_mult1
  ctx.define_pins(t)
