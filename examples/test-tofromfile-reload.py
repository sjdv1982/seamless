import seamless
f = "test-tofromfile.seamless"
f2 = "test-tofromfile-reload.seamless"
ctx = seamless.context()
from seamless.core.macro import _macros
_macros.clear()
ctx = seamless.fromfile(f)

import time
time.sleep(0.1)
c_output = ctx.cont.output.cell()
print(c_output.data)
ctx.cont.value.cell().set(10)
time.sleep(0.01)
print(c_output.data)
ctx.cont.code.cell().set("return value**2")
time.sleep(0.01)
print(c_output.data)

ctx.tofile(f2)

ctx = seamless.fromfile(f2, backup=False)
time.sleep(0.1)
c_output = ctx.cont.output.cell()
print(c_output.data)
ctx.cont.code.cell().set("return value*2")
time.sleep(0.01)
print(c_output.data)
ctx.cont.value.cell().set(4)
time.sleep(0.01)
print(c_output.data)
