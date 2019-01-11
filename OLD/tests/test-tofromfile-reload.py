import seamless
f = "test-tofromfile.seamless"
f2 = "test-tofromfile-reload.seamless"
ctx = seamless.context()
from seamless.core.macro import _macros
_macros.clear()
ctx = seamless.fromfile(f)

ctx.equilibrate()
c_output = ctx.cont.output.cell()
print(c_output.data)
ctx.cont.value.cell().set(10)
ctx.equilibrate()
print(c_output.data)
ctx.cont.code.cell().set("return value**2")
ctx.equilibrate()
print(c_output.data)

ctx.tofile(f2, backup=False)

ctx = seamless.fromfile(f2)
ctx.equilibrate()
c_output = ctx.cont.output.cell()
print(c_output.data)
ctx.cont.code.cell().set("return value*2")
ctx.equilibrate()
print(c_output.data)
ctx.cont.value.cell().set(4)
ctx.equilibrate()
print(c_output.data)
