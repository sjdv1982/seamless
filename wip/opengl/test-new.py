import seamless
from seamless import context, editor
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
ctx.ed = editor(pinparams)
link(ctx.ed.code_start.cell(), ".", "cell-test-new.py")
ctx.ed.code_update.cell().set("do_update()")
ctx.ed.code_stop.cell().set("")
ctx.glwindow.init.cell().connect(ctx.ed.init)
ctx.glwindow.paint.cell().connect(ctx.ed.paint)
ctx.glwindow.show.cell().set()
