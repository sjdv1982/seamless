from collections import OrderedDict
from seamless import editor, macro
from seamless.core.cell import Cell

@macro(OrderedDict((
    ("dtype",{"type": "dtype", "default": ("text", "html")}),
    ("title",{"type": "str", "default": "Browser"})
)))
def browser(ctx, dtype, title):
    from seamless import editor
    assert dtype[:2] == ("text", "html") #for now...
    pinparams = {
      "value": {
        "pin": "edit",
        "dtype": dtype
      },
      "title": {
        "pin": "input",
        "dtype": "str",
      },
    }
    ed = ctx.ed = editor(pinparams)
    ed.title.cell().set(title)
    ed.code_start.cell().fromfile("cell-browser.py")
    ed.code_stop.cell().set('widget.destroy()')
    c_up = ed.code_update.cell(True)
    c_up.fromfile("cell-browser_UPDATE.py")
    ctx.export(ed, forced=["title"])

def browse(cell, title=None, own=False):
    assert isinstance(cell, Cell)
    assert cell.context is not None
    ed = browser(cell.dtype, title)
    cell.connect(ed.value)
    if own:
        cell.own(ed)
    ed._validate_path()
    return ed
