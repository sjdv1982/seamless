from collections import OrderedDict
from seamless import reactor, macro
from seamless.core.cell import Cell

@macro(OrderedDict((
    ("dtype",{"type": "dtype", "default": ("text", "html")}),
    ("title",{"type": "str", "default": "Browser"})
)))
def browser(ctx, dtype, title):
    from seamless import reactor
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
    rc = ctx.rc = reactor(pinparams)
    rc.title.cell().set(title)
    rc.code_start.cell().fromfile("cell-browser.py")
    rc.code_stop.cell().set('widget.destroy()')
    c_up = rc.code_update.cell(True)
    c_up.fromfile("cell-browser_UPDATE.py")
    ctx.export(rc, forced=["title"])

def browse(cell, title=None, own=False):
    assert isinstance(cell, Cell)
    assert cell.context is not None
    b = browser(cell.dtype, title)
    cell.connect(b.value)
    if own:
        cell.own(b)
    b._validate_path()
    return b
