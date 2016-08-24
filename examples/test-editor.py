import os
import sys
import time

from contextlib import contextmanager

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


@contextmanager
def open_relative(filename, mode='r'):
    with open(os.path.join(os.path.dirname(__file__), filename), mode) as f:
        yield f


def make_editor(ed, directory):
    with open_relative("{}/start.py".format(directory)) as f_start, \
            open_relative("{}/update.py".format(directory)) as f_update, \
            open_relative("{}/stop.py".format(directory)) as f_stop:

        ed.code_start.cell().set(f_start.read())
        ed.code_stop.cell().set(f_stop.read())
        ed.code_update.cell().set(f_update.read())

editor_1 = ctx.processes.editor1(editor(eparams))
editor_2 = ctx.processes.editor2(editor(eparams))

editor_1.title.cell().set("Editor #1")
editor_2.title.cell().set("Editor #2")

make_editor(editor_1, "editor_spin")
make_editor(editor_2, "editor_spin")

c_data.connect(editor_1.value)
editor_1.output.solid.connect(c_data)
c_output.connect(editor_2.value)

# text_editor_1 = ctx.processes.text_editor_1(editor(teparams))
text_editor_1 = ctx.processes.text_editor1(editor(teparams2))
make_editor(text_editor_1, "editor_text")
# c = editor_1.title.cell()
c = c_code
v = text_editor_1.value.cell()
# v.set("Test!!")

print(c_code, text_editor_1)
# c.connect(text_editor_1.value)
# text_editor_1.output.solid.connect(c)
