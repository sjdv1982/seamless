import os
import sys
import time

from seamless import context, cell, transformer, editor, macro
from seamless.lib.gui.basic_editor import edit
from seamless.lib.gui.basic_display import display
ctx = context()

@macro({"formula": {"type": "str", "default": "return value*2"}})
def operator(ctx, formula ):
    from seamless import cell, transformer
    tparams = ctx.tparams = cell("object").set(
    {
      "value": {
        "pin": "input",
        "dtype": "int"
      },
      "output": {
        "pin": "output",
        "dtype": "int"
      }
    }
    )

    cont = ctx.cont = transformer(tparams)
    c_code = cont.code.cell()
    c_code.set(formula)
    ctx.export(cont)

op = operator()
c_data = op.value.cell()
c_data.set(4)
c_output = op.output.cell()
c_code = op.cont.code.cell()

time.sleep(0.001)
# 1 ms is usually enough to print "8", try 0.0001 for a random chance
print("VALUE", c_data.data, "'" + c_code.data + "'", c_output.data)

c_data.set(5)
c_code.set("return value*3")

time.sleep(0.001)
# 1 ms is usually enough to print "8", try 0.0001 for a random chance
print("VALUE", c_data.data, "'" + c_code.data + "'", c_output.data)

ed1 = ctx.ed1 = edit(c_data)
ed2 = ctx.ed2 = display(c_output)
ed1.title.cell().set("Input")
ed2.title.cell().set("Output")

ted1 = ctx.ted1 = edit(c_code)
ted1.title.cell().set("Formula editor")

meta_ted = ctx.meta_ted = edit(ted1.ed.code_start.cell())
meta_ted.title.cell().set("Meta-editor")
