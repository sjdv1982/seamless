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

import seamless
from seamless import context, transformer
ctx = context()

cont = ctx.cont = transformer(tparams)
c_data = cont.value.cell()
c_data.set(4)
c_code = cont.code.cell()
c_output = cont.output.cell()
c_code.set("return value*2")

import time
time.sleep(0.1)
print(c_output.data)

f = "test-tofromfile.seamless"
ctx.tofile(f)
ctx.destroy()

ctx = seamless.fromfile(f)
