import os
import sys
import time

from seamless import context, cell, transformer, editor, macro
ctx = context()

@macro({"formula": {"type": "str", "default": "return value*2"}})
def operator(ctx, formula ):
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




eparams = ctx.eparams = cell("object").set(
{
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
)

teparams = {
  "value": {
    "pin": "input",
    "dtype": "str"
  },
  "title": {
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
  "title": {
    "pin": "input",
    "dtype": "str"
  },
  "output": {
    "pin": "output",
    "dtype": ("text", "code", "python")
  }
}

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

editor_pycell =  os.path.join(
  os.path.dirname(__file__), "test-editor_pycell.py"
)
editor_pycell2 =  os.path.join(
  os.path.dirname(__file__), "test-editor_pycell2.py"
)

@macro("json",with_context=False)
def make_editor(ed):
    ed = editor(eparams)
    ed.code_start.cell().fromfile(editor_pycell)
    ed.code_stop.cell().set('_cache["w"].destroy()')
    ed.code_update.cell().set("""
b, w = _cache["b"], _cache["w"]
b.setValue(value)
w.setWindowTitle(title)
""")
    return ed

@macro("json",with_context=False)
def make_text_editor(eparams):
    ed = editor(eparams)
    ed.code_start.cell().fromfile(editor_pycell2)
    ed.code_stop.cell().set('_cache["w"].destroy()')
    ed.code_update.cell().set("""
b, w = _cache["b"], _cache["w"]
if value != b.toPlainText():
    b.setText(value)
w.setWindowTitle(title)
""")
    return ed

ed1 = ctx.ed1 = make_editor(eparams)
ed2 = ctx.ed2 = make_editor(eparams)
ed1.title.cell().set("Editor #1")
ed2.title.cell().set("Editor #2")
c_data.connect(ed1.value)
ed1.output.solid.connect(c_data)
c_output.connect(ed2.value)

#ted1 = ctx.ted1 = make_text_editor(teparams)
ted1 = ctx.ted1 = make_text_editor(teparams2)
ted1.title.cell().set("Formula editor")
#c = ed1.title.cell()
c = c_code
#v = ted1.value.cell()
#v.set("Test!!")
c.connect(ted1.value)
ted1.output.solid.connect(c)

meta_ted = ctx.meta_ted = make_text_editor(teparams2)
meta_ted.title.cell().set("Meta-editor")
c = ted1.code_start.cell()
#v = meta_ted1.value.cell()
#v.set("Test!!")
c.connect(meta_ted.value)
meta_ted.output.solid.connect(c)
