from seamless import macro
from collections import OrderedDict

@macro(OrderedDict((
    ("program",{"type": "json"}),
    ("with_window", {"type": "bool", "default": True}),
    ("window_title", {"type": "string", "default": "GLProgram"}),
)))
def glprogram(ctx, program, with_window, window_title):
    from seamless import cell, reactor, macro
    from seamless.core.worker import ExportedInputPin, ExportedOutputPin, \
      ExportedEditPin
    from seamless.lib.gui.gl.glwindow import glwindow

    arrays = program["arrays"]
    textures = program.get("textures", [])

    rcparams = {

      #signals
      "init": {
        "pin": "input",
        "dtype": "signal",
      },
      "paint": {
        "pin": "input",
        "dtype": "signal",
      },
      "repaint": {
        "pin": "output",
        "dtype": "signal",
      },

      #shaders
      "vertex_shader": {
        "pin": "input",
        "dtype": ("text", "code", "vertexshader"),
      },
      "fragment_shader": {
        "pin": "input",
        "dtype": ("text", "code", "fragmentshader"),
      },

      #program
      "program": {
        "pin": "input",
        "dtype": "json",
      },

      #uniforms
      "uniforms" : {
        "pin": "input",
        "dtype": "json"
      }
    }
    for ar in arrays:
        rcparams["array_" + ar] = {"pin": "input","dtype": "array"}

    for ar in textures:
        assert ar not in program["arrays"], ar
        rcparams["array_" + ar] = {"pin": "input","dtype": "array"}

    ctx.rcparams = cell("json").set(rcparams)
    ctx.rc = reactor(ctx.rcparams)
    ctx.rc.code_start.cell().fromfile("cell-glprogram.py")
    ctx.rc.code_update.cell().set("do_update()")
    ctx.rc.code_stop.cell().set("")
    ctx.rc.program.cell().set(program)

    if with_window:
        ctx.glwindow = glwindow(window_title)
        ctx.glwindow.init.cell().connect(ctx.rc.init)
        ctx.glwindow.paint.cell().connect(ctx.rc.paint)
        ctx.rc.repaint.cell().connect(ctx.glwindow.update)
        ctx.update = ExportedInputPin(ctx.glwindow.update)
        ctx.painted = ExportedOutputPin(ctx.glwindow.painted)
        ctx.camera = ExportedEditPin(ctx.glwindow.camera)
        ctx.last_key = ExportedOutputPin(ctx.glwindow.last_key)
    ctx.export(ctx.rc)
