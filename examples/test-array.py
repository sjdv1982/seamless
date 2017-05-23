import seamless
from seamless import cell, context, transformer, reactor
from seamless.lib.gui.basic_editor import edit
from seamless.lib.gui.basic_display import display
import numpy as np

ctx = context()
a1 = np.arange(10,20,1)
a2 = np.arange(100,120,2)
ctx.array1 = cell("array").set(a1)
ctx.array2 = cell("array").set(a2)
ctx.tf = transformer({"a1": {"pin": "input", "dtype": "array"},
                      "a2": {"pin": "input", "dtype": "array"},
                      "a3": {"pin": "output", "dtype": "array"}})
ctx.array1.connect(ctx.tf.a1)
ctx.array2.connect(ctx.tf.a2)
ctx.tf.code.cell().set("print('RUN');import numpy as np; return np.concatenate((a1,a2))")
ctx.equilibrate()
print(ctx.tf.a3.cell().value)

ctx.array1.enable_store("GL")
ctx.rc = reactor({"a1": {"pin": "input", "dtype": "array"}})
ctx.array1.connect(ctx.rc.a1)
ctx.rc.code_start.cell().set("")
ctx.rc.code_stop.cell().set("")
ctx.rc.code_update.cell().set("""
store = PINS.a1.store
store.bind() #We won't get an actual OpenGL ID since there is no OpenGL context...
print("OpenGL ID", store.opengl_id, "State", store._state, store.shape)
print(PINS.a1.get())
print("OK")
""")

ctx.equilibrate()
ctx.array1.set(np.ones(12))
ctx.equilibrate()
print(ctx.tf.a3.cell().value)
