from collections import OrderedDict
from seamless import reactor, macro
from seamless.core.cell import Cell

@macro(OrderedDict((
    ("dtype","dtype"),
    ("options","json"),
    ("title",{"type": "str", "default": "Combobox"})
)), with_context=False)
def combobox(dtype, options, title):
    from seamless import reactor
    pinparams = {
      "value": {
        "pin": "edit",
        "dtype": dtype,
        "must_be_defined": False
      },
      "options": {
        "pin": "input",
        "dtype": "json",
      },
      "title": {
        "pin": "input",
        "dtype": "str",
      },
    }
    rc = reactor(pinparams)
    rc.options.cell().set(options)
    rc.title.cell().set(title)
    rc.code_start.cell().fromfile("cell-combobox.py")
    rc.code_stop.cell().set('widget.destroy()')
    c_up = rc.code_update.cell(True)
    c_up.fromfile("cell-combobox_UPDATE.py")
    return rc
