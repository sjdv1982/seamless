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

if __name__ == "__main__":
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
    print(c_data.data, "'" + c_code.data + "'", c_output.data)

    c_data.set(5)
    c_code.set("return value*3")

    ed = ctx.processes.ed(editor(tparams))
    c_output.connect(ed.value)
    ed.code_start.cell().set("""
print("START QSpinBox!")
from seamless.qt.QtWidgets import QSpinBox
from seamless.qt.QtCore import Qt
b = QSpinBox()
b.setWindowFlags(Qt.WindowStaysOnTopHint)
b.show()
_cache["b"] = b
    """)
    ed.code_stop.cell().set('_cache["b"].destroy()')
    ed.code_update.cell().set('_cache["b"].setValue(value)')
