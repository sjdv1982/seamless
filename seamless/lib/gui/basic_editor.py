from collections import OrderedDict
from seamless import reactor, macro
from seamless.core.cell import Cell
from seamless.core.context import active_context_as

import os, glob
from seamless.core import libmanager
for f in glob.glob(os.path.dirname(__file__) + os.sep + "cell-basic_editor*.py"):
    ff = os.path.split(f)[1]
    libmanager.load(ff)


@macro(OrderedDict((
    ("editor_type","str"),
    ("title",{"type": "str", "default": "Basic editor"})
)))
def basic_editor(ctx, editor_type, title):
    from seamless import reactor

    _editors = {
      "int": {
        "code": "cell-basic_editor_int.py",
        "update": "cell-basic_editor_int_UPDATE.py",
      },
      "float": {
        "code": "cell-basic_editor_float.py",
        "update": "cell-basic_editor_UPDATE.py",
      },
      "text": {
        "code": "cell-basic_editor_text.py",
        "update": "cell-basic_editor_text_UPDATE.py",
      },
      "json": {
        "code": "cell-basic_editor_json.py",
        "update": "cell-basic_editor_json_UPDATE.py",
      },
    }

    def _match_type(type, typelist):
        typelist = list(typelist)
        type2 = type
        if isinstance(type, str):
            type2 = (type,)
        typelist2 = []
        for t in typelist:
            if isinstance(t, str):
                typelist2.append((t,))
            else:
                typelist2.append(t)
        matches = []
        for n in range(len(typelist)):
            ltype = typelist2[n]
            k = min(len(type2), len(ltype))
            if type2[:k] == ltype[:k]:
                matches.append((n, k))
        if not len(matches):
            raise TypeError("Cannot find editor for cell type '{0}'".format(type))
        matches.sort(key=lambda v: -v[1])
        bestmatch = matches[0][0]
        return typelist[bestmatch]

    editor_type = _match_type(editor_type, _editors.keys())
    pinparams = {
      "value": {
        "pin": "edit",
        "dtype": editor_type,
        "must_be_defined": False
      },
      "title": {
        "pin": "input",
        "dtype": "str",
      },
    }
    if editor_type == "int":
        pinparams["maximum"] = {"pin": "input", "dtype": "int"}
    rc = ctx.rc = reactor(pinparams)
    rc.title.cell().set(title)
    forced = ["title"]
    if editor_type == "int":
        rc.maximum.set(9999999)
        forced.append("maximum")
    rc.code_start.cell().fromfile(_editors[editor_type]["code"])
    rc.code_stop.cell().set('w.destroy()')
    upfile = _editors[editor_type]["update"]
    c_up = rc.code_update.cell(True)
    if upfile is not None:
        c_up.fromfile(upfile)
    else:
        c_up.set("")
    ctx.export(rc, forced=forced)

def edit(cell, title=None, own=False):
    assert isinstance(cell, Cell)
    assert cell.context is not None
    ed = basic_editor(cell.dtype, title)
    cell.connect(ed.value)
    if own:
        try:
            cell.own(ed)
        except Exception:
            pass
    return ed
