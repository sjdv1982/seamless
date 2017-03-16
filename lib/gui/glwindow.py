from seamless import editor, macro
from collections import OrderedDict

@macro(OrderedDict((
    ("title",{"type": "str", "default": "OpenGL window"}),
    ("size", {"type": "json", "default": (640, 480)}),
    ("position", {"type": "json", "default": (0, 0)}),
)), with_context=False)
def glwindow(title, size, position):
    from seamless import editor
    pinparams = {
      "title": {
        "pin": "input",
        "dtype": "str"
      },
      "geometry": {
        "pin": "input",
        "dtype": "json"
      },
      "update": {
        "pin": "input",
        "dtype": "signal"
      },
      "init": {
        "pin": "output",
        "dtype": "signal",
      },
      "paint": {
        "pin": "output",
        "dtype": "signal",
      },
      "show": {
        "pin": "input",
        "dtype": "signal",
      },
    }
    ed = editor(pinparams)
    ed.title.cell().set(title)
    geometry = list(position) + list(size)
    assert len(geometry) == 4, geometry
    ed.geometry.cell().set(geometry)
    ed.code_start.cell().fromfile("cell-glwindow.py")
    ed.code_update.cell().set('do_update()')
    ed.code_stop.cell().set('widget.destroy()')
    return ed
