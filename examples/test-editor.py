import os
import sys
import time

tparams = {
  "value": {
    "pin": "input",
    "dtype": "int"
  },
  "outp": {
    "pin": "output",
    "dtype": "int"
  },
}

eparams = {
  "value": {
    "pin": "edit",
    "dtype": "int"
  },
  "title": {
    "pin": "input",
    "dtype": "str"
  },
}

teparams = {
  "value": {
    "pin": "edit",
    "dtype": "str"
  },
  "title": {
    "pin": "input",
    "dtype": "str"
  },
}

teparams2 = {
  "value": {
    "pin": "edit",
    "dtype": ("text", "code", "python")
  },
  "title": {
    "pin": "input",
    "dtype": "str"
  },
}

from seamless import context, transformer, editor
ctx = context()

cont = ctx.cont = transformer(tparams)
c_data = cont.value.cell()
c_data.set(4)
c_code = cont.code.cell()
c_output = cont.outp.cell()
c_code.set("return value*2")

ctx.equilibrate()
print("VALUE", c_data.data, "'" + c_code.data + "'", c_output.data)

c_data.set(5)
c_code.set("return value*3")

editor_pycell =  os.path.join(
  os.path.dirname(__file__), "test-editor_pycell.py"
)
editor_pycell2 =  os.path.join(
  os.path.dirname(__file__), "test-editor_pycell2.py"
)

def make_editor(ed):
    ed.code_start.cell().fromfile(editor_pycell)
    ed.code_stop.cell().set('w.destroy()')
    ed.code_update.cell().set("""
if PINS.value.updated:
    b.setValue(PINS.value.get())
if PINS.title.updated:
    w.setWindowTitle(PINS.title.get())
""")

def make_text_editor(ed):
    ed.code_start.cell().fromfile(editor_pycell2)
    ed.code_stop.cell().set('w.destroy()')
    ed.code_update.cell().set("""
if PINS.value.updated:
    b.setText(PINS.value.get())
if PINS.title.updated:
    w.setWindowTitle(PINS.title.get())
""")

ed1 = ctx.ed1 = editor(eparams)
ed2 = ctx.ed2 = editor(eparams)
ed1.title.cell().set("Editor #1")
ed2.title.cell().set("Editor #2")
make_editor(ed1)
make_editor(ed2)
c_data.connect(ed1.value)
c_output.connect(ed2.value)

#ted1 = ctx.ted1 = editor(teparams)
ted1 = ctx.ted1 = editor(teparams2)
ted1.title.cell().set("Formula editor")
make_text_editor(ted1)
#c = ed1.title.cell()
c = c_code
#v = ted1.value.cell()
#v.set("Test!!")
c.connect(ted1.value)

meta_ted = ctx.meta_ted = editor(teparams2)
meta_ted.title.cell().set("Meta-editor")
make_text_editor(meta_ted)
c = ted1.code_start.cell()
#v = meta_ted1.value.cell()
#v.set("Test!!")
c.connect(meta_ted.value)
