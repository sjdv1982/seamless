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
    ed = ctx.processes.ed(editor(pinparams))
    ed.set_context(ctx) #TODO: should not be necessary...
    ed.title.cell(True).set(title)
    ed.code_start.cell(True).fromfile(_editors[editor_type]["code"])
    ed.code_stop.cell(True).set('_cache["w"].destroy()')
    ed.code_update.cell(True).fromfile(_editors[editor_type]["update"])
    ed.value.cell().set(10)
    ed.output.solid.connect(ed.value.cell())
    #ctx.export(ed)

def edit(cell, solid=True):
    assert isinstance(cell, Cell)
    assert cell.context is not None
    with active_context_as(cell.context):
        ed = basic_editor(cell.dtype)
    """
    cell.connect(ed.value)
    if solid:
        ed.output.solid.connect(cell)
    else:
        ed.output.liquid.connect(cell)
    cell.own(ed)
    """
    return ed
