from seamless import reactor, macro
from collections import OrderedDict

@macro(OrderedDict((
    ("title",{"type": "str", "default": "OpenGL window"}),
    ("size", {"type": "json", "default": (640, 480)}),
    ("position", {"type": "json", "default": (0, 0)}),
)), with_context=False)
def glwindow(title, size, position):
    from seamless import reactor
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
      "camera": {
        "pin": "edit",
        "dtype": "json",
        "must_be_defined": False
      },
      "init": {
        "pin": "output",
        "dtype": "signal",
      },
      "paint": {
        "pin": "output",
        "dtype": "signal",
      },
      "painted": {
        "pin": "output",
        "dtype": "signal"
      },
      "last_key": {
        "pin": "output",
        "dtype": "str"
      }
    }
    rc = reactor(pinparams)
    rc.title.cell().set(title)
    geometry = list(position) + list(size)
    assert len(geometry) == 4, geometry
    rc.geometry.cell().set(geometry)
    rc.code_start.cell().fromfile("cell-glwindow.py")
    rc.code_update.cell().set('do_update()')
    rc.code_stop.cell().set('widget.destroy()')
    return rc
