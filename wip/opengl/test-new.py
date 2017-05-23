import seamless
from seamless import context, reactor
from seamless.lib.filelink import link
from seamless.lib.gui.glwindow import glwindow
import numpy as np

ctx = context()
ctx.glwindow = glwindow()
pinparams = {
  "init": {
    "pin": "input",
    "dtype": "signal",
  },
  "paint": {
    "pin": "input",
    "dtype": "signal",
  },
  "data_default" : {
    "pin": "input",
    "dtype": "array",
  },
  "data_indices" : {
    "pin": "input",
    "dtype": "array",
  }
}

# Build data
data = np.zeros(4, [("position", np.float32, 2),
                         ("color",    np.float32, 4)])
data['color'] = [(1, 0, 0, 1), (0, 1, 0, 1),
                      (0, 0, 1, 1), (1, 1, 0, 1)]
data['position'] = [(-1, -1), (-1, +1),
                         (+1, -1), (+1, +1)]

indices = np.array((1,2,3,0,1,2),dtype=np.uint16)

ctx.rc = reactor(pinparams)
c = ctx.rc.data_default.cell()
c.enable_store("GL")
c.set(data)

c = ctx.rc.data_indices.cell()
c.enable_store("GL")
c.set(indices)

link(ctx.rc.code_start.cell(), ".", "cell-test-new.py")
ctx.rc.code_update.cell().set("do_update()")
ctx.rc.code_stop.cell().set("")
ctx.glwindow.init.cell().connect(ctx.rc.init)
ctx.glwindow.paint.cell().connect(ctx.rc.paint)
ctx.glwindow.show.cell().set()
