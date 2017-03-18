from collections import OrderedDict
from seamless import editor, macro
from seamless.core.cell import Cell

@macro(OrderedDict((
    ("dtype","dtype"),
    ("options","json"),
    ("title",{"type": "str", "default": "Combobox"})
)), with_context=False)
def combobox(dtype, options, title):
    from seamless import editor
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
    ed = editor(pinparams)
    ed.options.cell().set(options)
    ed.title.cell().set(title)
    ed.code_start.cell().fromfile("cell-combobox.py")
    ed.code_stop.cell().set('widget.destroy()')
    c_up = ed.code_update.cell(True)
    c_up.fromfile("cell-combobox_UPDATE.py")
    return ed
