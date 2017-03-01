import seamless
from seamless import context, editor, cell
from seamless.lib.filelink import link
ctx = context()
ctx.sender = editor({"outp": {"pin": "output", "dtype": "signal"}})
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
ctx.receiver = editor({"inp": {"pin": "input", "dtype": "signal"},
                       "inp2": {"pin": "input", "dtype": "int"}})
ctx.signal.connect(ctx.receiver.inp)
ctx.receiver.code_start.cell().set("")
ctx.receiver.code_update.cell().set("""
if PINS.inp.updated:
    print('Signal received')
else:
    print("Signal was not updated")
""")
ctx.receiver.code_stop.cell().set("")
ctx.receiver.inp2.cell().set(0)
print("START")
print("Sending one manual signal...")
ctx.signal.set()
print("... done")
print("Updating the secondary input...")
ctx.receiver.inp2.cell().set(1)
print("... done")

import os
ctx.tofile(os.path.splitext(__file__)[0] + ".seamless", backup=False)
