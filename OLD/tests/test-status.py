from seamless import cell, context, transformer, reactor
from seamless import export

ctx = context()
tf = ctx.tf = transformer({
    "inp": {"pin": "input", "dtype": "int"},
    "outp": {"pin": "output", "dtype": "int"},
})
print(tf.outp.status())
print(tf.status())
export(tf.inp)
ctx.inp.set(2)
try:
    ctx.inp.set("a")
except Exception:
    pass
print(tf.status())
export(tf.outp)
print(tf.status())
export(tf.code)
print(tf.status())
tf.code.set("return inp + 42")
print(tf.status())
tf.inp.set(0)
print(tf.status())
ctx.equilibrate()
print(tf.status())
ctx.inp.disconnect(tf.inp)
print(tf.status())

rc = ctx.rc = reactor({
    "inp2": {"pin": "input", "dtype": "int"},
    "outp2": {"pin": "output", "dtype": "int"},
})
rc.code_start.cell().set("")
rc.code_stop.cell().set("")
rc.code_update.cell().set("PINS.outp2.set(PINS.inp2.get()+42)")
export(rc.outp2)
print(rc.status())
print(ctx.status())
export(rc.inp2)
ctx.inp.connect(tf.inp)
print(ctx.status())
ctx.inp2.set(12)
print(ctx.status())
