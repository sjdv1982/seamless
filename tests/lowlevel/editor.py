import os
import sys
import time

tparams = {
  "val": "input",
  "outp": "output",
}

eparams = {
  "val": "edit",
  "title": "input",
}

teparams = {
  "val": "edit",
  "title": "input",
}

from seamless.core import macro_mode_on
from seamless.core import context, transformer, reactor, cell

with macro_mode_on():
  ctx = context(toplevel=True)
  ctx.formula = cell("text").mount("/tmp/formula.txt")  
  ctx.formula2 = cell("text").mount("/tmp/formula2.txt")
tf = ctx.tf = transformer(tparams)
c_data = tf.val.cell()
c_data.set(4)
#c_code = tf.code.cell()
ctx.formula.connect(tf.code)
c_code = ctx.formula
c_output = tf.outp.cell()
c_code.set("outp = val*2")

c_output2 = ctx.c_output2 = cell("plain").set(-1) # Must be initialized

rc = ctx.rc = reactor({
  "x": "input",
  "xcopy": "edit",
})
c_output.connect(rc.x)
c_output2.connect(rc.xcopy)  # or: rc.xcopy.connect(c_output2)
rc.code_start.cell().set("")
rc.code_stop.cell().set("")
rc.code_update.cell().set(
  """
if PINS.x.updated:
    PINS.xcopy.set(PINS.x.get())
  """
)

ctx.compute()
print("VALUE", c_data.value, "'" + c_code.value + "'", c_output.value)

c_data.set(5)
c_code.set("outp = val*3")
ctx.compute()

editor_pycell =  os.path.join(
  os.path.dirname(__file__), "editor_pycell.py"
)
editor_pycell2 =  os.path.join(
  os.path.dirname(__file__), "editor_pycell2.py"
)

def make_editor(ed):
    ed.code_start.cell().from_file(editor_pycell)
    ed.code_stop.cell().set('w.destroy()')
    ed.code_update.cell().set("""
if PINS.val.updated:
    b.setValue(PINS.val.get())
if PINS.title.updated:
    w.setWindowTitle(PINS.title.get())
""")

def make_text_editor(ed):
    ed.code_start.cell().from_file(editor_pycell2)
    ed.code_stop.cell().set('w.destroy()')
    ed.code_update.cell().set("""
if PINS.val.updated:    
    b.setText(PINS.val.get())
if PINS.title.updated:
    w.setWindowTitle(PINS.title.get())
""")


ed1 = ctx.ed1 = reactor(eparams)
ed2 = ctx.ed2 = reactor(eparams)
ed1.title.cell("text").set("Editor #1")
ed2.title.cell("text").set("Editor #2")
make_editor(ed1)
make_editor(ed2)
c_data.connect(ed1.val)
ctx.compute()
c_output2.connect(ed2.val)

ted1 = ctx.ted1 = reactor(teparams)
ted1.title.cell().set("Formula editor")
make_text_editor(ted1)
c = c_code
c.connect(ted1.val)

meta_ted = ctx.meta_ted = reactor(teparams)
meta_ted.title.cell().set("Meta-editor")
make_text_editor(meta_ted)
ctx.compute()

c = ted1.code_start.cell()
c.connect(meta_ted.val)

ctx.formula.highlink(ctx.formula2)
ctx.compute()
