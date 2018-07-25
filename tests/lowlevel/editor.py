import os
import sys
import time

tparams = {
  "value": "input",
  "outp": "output",
}

eparams = {
  "value": {"io": "edit", "mode": "copy"},
  "title": "input",
}

teparams = {
  "value": {"io": "edit", "mode": "copy"},
  "title": "input",
}

from seamless.core import macro_mode_on
from seamless.core import context, transformer, reactor
with macro_mode_on():
    ctx = context(toplevel=True)

    cont = ctx.cont = transformer(tparams)
    c_data = cont.value.cell()
    c_data.set(4)
    c_code = cont.code.cell()
    c_output = cont.outp.cell()
    c_code.set("outp = value*2")

ctx.equilibrate()
print("VALUE", c_data.value, "'" + c_code.value + "'", c_output.value)

c_data.set(5)
c_code.set("outp = value*3")

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
if PINS.value.updated:
    b.setValue(PINS.value.get())
if PINS.title.updated:
    w.setWindowTitle(PINS.title.get())
""")

def make_text_editor(ed):
    ed.code_start.cell().from_file(editor_pycell2)
    ed.code_stop.cell().set('w.destroy()')
    ed.code_update.cell().set("""
if PINS.value.updated:
    b.setText(PINS.value.get())
if PINS.title.updated:
    w.setWindowTitle(PINS.title.get())
""")

with macro_mode_on():
    ed1 = ctx.ed1 = reactor(eparams)
    ed2 = ctx.ed2 = reactor(eparams)
    ed1.title.cell("text").set("Editor #1")
    ed2.title.cell("text").set("Editor #2")
    make_editor(ed1)
    make_editor(ed2)
    c_data.connect(ed1.value)
    c_output.connect(ed2.value)
    ted1 = ctx.ted1 = reactor(teparams)
    ted1.title.cell().set("Formula editor")
    make_text_editor(ted1)
    c = ed1.title.cell()
    c = c_code
    c.connect(ted1.value)

    meta_ted = ctx.meta_ted = reactor(teparams)
    meta_ted.title.cell().set("Meta-editor")
    make_text_editor(meta_ted)
    c = ted1.code_start.cell()
    c.connect(meta_ted.value)
