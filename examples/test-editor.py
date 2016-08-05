import os
import sys
import time

tparams = {
  "value": {
    "pin": "input",
    "dtype": "int"
  },
  "output": {
    "pin": "output",
    "dtype": "int"
  }
}

eparams = {
  "value": {
    "pin": "input",
    "dtype": "int"
  },
  "title": {
    "pin": "input",
    "dtype": "str"
  },
  "output": {
    "pin": "output",
    "dtype": "int"
  }
}

teparams = {
  "value": {
    "pin": "input",
    "dtype": "str"
  },
  "output": {
    "pin": "output",
    "dtype": "str"
  }
}

teparams2 = {
  "value": {
    "pin": "input",
    "dtype": ("text", "code", "python")
  },
  "output": {
    "pin": "output",
    "dtype": ("text", "code", "python")
  }
}

dir_containing_seamless = os.path.normpath(
 os.path.join(os.path.dirname(__file__), '../../')
)
sys.path.append(dir_containing_seamless)

from seamless import context, transformer, editor
ctx = context()

cont = ctx.processes.cont(transformer(tparams))
c_data = cont.value.cell()
c_data.set(4)
c_code = cont.code.cell()
c_output = cont.output.cell()
c_code.set("return value*2")

time.sleep(0.001)
# 1 ms is usually enough to print "8", try 0.0001 for a random chance
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
    ed.code_start.cell().set(open(editor_pycell).read())
    ed.code_stop.cell().set('_cache["w"].destroy()')
    ed.code_update.cell().set("""
b, w = _cache["b"], _cache["w"]
b.setValue(value)
w.setWindowTitle(title)
""")

def make_text_editor(ed):
    ed.code_start.cell().set(open(editor_pycell2).read())
    ed.code_stop.cell().set('_cache["w"].destroy()')
    ed.code_update.cell().set("""
b, w = _cache["b"], _cache["w"]
if value != b.toPlainText():
    b.setText(value)
""")

ed1 = ctx.processes.ed1(editor(eparams))
ed2 = ctx.processes.ed2(editor(eparams))
ed1.title.cell().set("Editor #1")
ed2.title.cell().set("Editor #2")
make_editor(ed1)
make_editor(ed2)
c_data.connect(ed1.value)
ed1.output.solid.connect(c_data)
c_output.connect(ed2.value)

#ted1 = ctx.processes.ted1(editor(teparams))
ted1 = ctx.processes.ted1(editor(teparams2))
make_text_editor(ted1)
#c = ed1.title.cell()
c = c_code
v = ted1.value.cell()
#v.set("Test!!")
c.connect(ted1.value)
ted1.output.solid.connect(c)
