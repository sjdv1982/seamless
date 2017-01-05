from collections import OrderedDict
from seamless import editor, macro
from seamless.core.cell import Cell
from seamless.core.context import active_context_as

_displays = {
#  "int": {
#    "code": "cell-basic_editor_int.py",
#    "update": "cell-basic_editor_UPDATE.py",
#  },
#  "float": {
#    "code": "cell-basic_editor_float.py",
#    "update": "cell-basic_editor_UPDATE.py",
#  },
  "text": {
    "code": "cell-basic_display_text.py",
    "update": "cell-basic_display_text_UPDATE.py",
  },
#  "json": {
#    "code": "cell-basic_editor_json.py",
#    "update": None
#  },
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
        raise TypeError("Cannot find display for cell type '{0}'".format(type))
    matches.sort(key=lambda v: -v[1])
    bestmatch = matches[0][0]
    return typelist[bestmatch]

@macro(OrderedDict((
    ("display_type","str"),
    ("title",{"type": "str", "default": "Basic display"})
)))
def basic_display(ctx, display_type, title):
    display_type = _match_type(display_type, _displays.keys())
    pinparams = {
      "value": {
        "pin": "input",
        "dtype": display_type
      },
      "title": {
        "pin": "input",
        "dtype": "str",
      },
    }
    d = ctx.display = editor(pinparams)
    d.title.cell().set(title)
    d.code_start.cell().fromfile(_displays[display_type]["code"])
    d.code_stop.cell().set('_cache["w"].destroy()')
    upfile = _displays[display_type]["update"]
    c_up = d.code_update.cell()
    if upfile is not None:
        c_up.fromfile(upfile)
    else:
        c_up.set("")
    ctx.export(d)

def display(cell, title=None):
    assert isinstance(cell, Cell)
    assert cell.context is not None
    with active_context_as(cell.context):
        d = basic_display(cell.dtype, title)
    cell.connect(d.value)
    #cell.own(d) #Bad idea. If cell gets re-created (e.g. by a macro),
    # the display won't be connected to any live cell
    return d
