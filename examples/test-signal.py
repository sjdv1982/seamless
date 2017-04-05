import seamless
from seamless import context, reactor, cell
from seamless.lib.filelink import link
ctx = context()
ctx.sender = reactor({"outp": {"pin": "output", "dtype": "signal"},
                       "outp2": {"pin": "output", "dtype": "int"}})
ctx.code = ctx.sender.code_start.cell()
link(ctx.code, ".", "test-signal_pycell.py")
ctx.sender.code_update.cell().set("")
ctx.sender.code_stop.cell().set("""
try:
    widget.destroy()
except:
    pass
""")
ctx.signal = ctx.sender.outp.cell()
ctx.value = ctx.sender.outp2.cell()
ctx.receiver = reactor({"inp": {"pin": "input", "dtype": "signal"},
                       "inp2": {"pin": "input", "dtype": "int"}})
ctx.signal.connect(ctx.receiver.inp)
ctx.value.connect(ctx.receiver.inp2)
ctx.receiver.code_start.cell().set("")
ctx.receiver.code_update.cell().set("""
if PINS.inp.updated:
    print('Receiver: signal received')
if PINS.inp2.updated:
    print("Receiver: secondary input was updated")
""")
ctx.receiver.code_stop.cell().set("")
ctx.value.set(0)
print("START")
print("Sending one manual signal...")
ctx.signal.set()
print("... done")
print("Updating the secondary input...")
ctx.value.set(1)
print("... done")

import os
ctx.tofile(os.path.splitext(__file__)[0] + ".seamless", backup=False)
