from .context import Context
from .editor import Editor
from .transformer import Transformer
from .cell import Cell
import json
from collections import OrderedDict

def _get_sl(parent, path):
    if len(path) == 0:
        return parent
    child = getattr(parent, path[0])
    return _get_sl(child, path[1:])

def find_sl(ctx, path):
    path2 = path.split(".")
    return _get_sl(ctx, path2)

from .fromfile_manager import json_to_connections

def json_to_lib(ctx, data):
    pass #TODO

def json_to_macro(ctx, data):
    from .macro import Macro, _macros
    for m in data:
        key = m["module_name"],  m["func_name"]
        assert tuple(m["dtype"]) == Macro.dtype, (m["dtype"] , Macro.dtype)
        macro = Macro(
          with_context=m["with_context"],
          type=tuple(m["type_args"]),
        )
        macro.module_name=m["module_name"]
        macro.func_name=m["func_name"]
        macro.update_code(m["code"])
        _macros[key] = macro

def json_to_cell(ctx, data, myname, ownerdict):
    dtype = data["dtype"]
    if isinstance(dtype, list):
        dtype = tuple(dtype)
    cell = Cell(dtype)
    if "data" in data:
        cell.set(data["data"])
    ctx._add_child(myname, cell)

    owner = data.get("owner", None)
    if owner is not None:
        ownerdict[cell] = owner

def json_to_process(ctx, data, myname, ownerdict):
    if data["type"] == "editor":
        assert data["mode"] == "sync", data["mode"]
        params = data["params"]
        child = Editor(params)
    elif data["type"] == "transformer":
        assert data["mode"] == "thread", data["mode"]
        params = data["params"]
        child = Transformer(params)
    ctx._add_child(myname, child)

    owner = data.get("owner", None)
    if owner is not None:
        ownerdict[child] = owner

def json_to_ctx(ctx, data, myname=None, ownerdict=None):

    from .process import InputPinBase, ExportedInputPin, \
      OutputPinBase, ExportedOutputPin, \
      EditPinBase, ExportedEditPin

    if myname is None:
        myctx = ctx
    else:
        myctx = Context(context=ctx,active_context=False)

    if ownerdict is None:
        ownerdict = OrderedDict()

    myctx._like_process = data["like_process"]
    myctx._like_cell = data["like_cell"]
    myctx._auto = set(data["auto"])
    for childname, c in sorted(data["children"].items()):
        if "type" not in c:
            json_to_cell(myctx, c, childname, ownerdict)
        elif c["type"] in ("editor", "transformer"):
            json_to_process(myctx, c, childname, ownerdict)
        elif c["type"] == "context":
            json_to_ctx(myctx, c, childname, ownerdict)
    if myname is not None:
        ctx._add_child(myname, myctx)

    owner = data.get("owner", None)
    if owner is not None:
        ownerdict[myctx] = owner

    if myname is None:
        for sl, ownerpath in ownerdict.items():
            owner = find_sl(ctx, ownerpath)
            owner.own(sl)

    for pinname, pinpath in sorted(data["pins"].items()):
        pin = find_sl(ctx, pinpath)
        if isinstance(pin, InputPinBase):
            ctx._pins[pinname] = ExportedInputPin(pin)
        elif isinstance(pin, OutputPinBase):
            ctx._pins[pinname] = ExportedOutputPin(pin)
        elif isinstance(pin, EditPinBase):
            ctx._pins[pinname] = ExportedEditPin(pin)
        else:
            raise TypeError(pin)


def fromfile(filename):
    import seamless
    data = json.load(open(filename))
    ctx = Context()
    json_to_lib(ctx, data["lib"])
    json_to_macro(ctx, data["macro"])
    json_to_ctx(ctx, data["main"])
    json_to_connections(ctx, data["main"])
    return ctx
