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

from seamless import context, transformer
ctx = context()

cont = ctx.cont = transformer(tparams)
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

cont2 = ctx.cont2 = transformer(tparams)
c_code.connect(cont2.code)
c_data.connect(cont2.value)
c_output2 = cont2.output.cell()

# c_output3 = cell("int")
# cont2.output.connect(c_output3)

cont.destroy()
# this will sync the controller I/O threads before killing them
cont2.destroy()
# this will sync the controller I/O threads before killing them
print(c_data.data, "'" + c_code.data + "'", c_output.data)
print(c_output2.data)
