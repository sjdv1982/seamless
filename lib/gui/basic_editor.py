from collections import OrderedDict
from seamless import editor, macro
from seamless.core.cell import Cell
from seamless.core.context import active_context_as

_editors = {
  "int": {
    "code": "cell-basic_editor_int.py",
    "update": "cell-basic_editor_UPDATE.py",
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
    "update": None #TODO
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

@macro(OrderedDict((
    ("editor_type","str"),
    ("title",{"type": "str", "default": "Basic editor"})
)))
def basic_editor(ctx, editor_type, title):
    editor_type = _match_type(editor_type, _editors.keys())
    pinparams = {
      "value": {
        "pin": "input",
        "dtype": editor_type
      },
      "title": {
        "pin": "input",
        "dtype": "str",
      },
      "output": {
        "pin": "output",
        "dtype": editor_type
      }
    }
    ed = ctx.ed = editor(pinparams)
    ed.title.cell().set(title)
    ed.code_start.cell().fromfile(_editors[editor_type]["code"])
    ed.code_stop.cell().set('_cache["w"].destroy()')
    upfile = _editors[editor_type]["update"]
    c_up = ed.code_update.cell(True)
    if upfile is not None:
        c_up.fromfile(upfile)
    else:
        c_up.set("")
    ctx.export(ed)

def edit(cell, title=None, solid=True, own=False):
    assert isinstance(cell, Cell)
    assert cell.context is not None
    from seamless.core.context import get_active_context
    ed = basic_editor(cell.dtype, title)
    cell.connect(ed.value)
    if solid:
        ed.output.solid.connect(cell)
    else:
        ed.output.liquid.connect(cell)
    if own:
        cell.own(ed)
    ed._validate_path()
    return ed
