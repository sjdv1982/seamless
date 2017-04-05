import seamless
from seamless import context, reactor
from seamless.lib.filelink import link
from seamless.lib.gui.glwindow import glwindow
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
}
ctx.rc = reactor(pinparams)
link(ctx.rc.code_start.cell(), ".", "cell-test-new.py")
ctx.rc.code_update.cell().set("do_update()")
ctx.rc.code_stop.cell().set("")
ctx.glwindow.init.cell().connect(ctx.rc.init)
ctx.glwindow.paint.cell().connect(ctx.rc.paint)
ctx.glwindow.show.cell().set()
