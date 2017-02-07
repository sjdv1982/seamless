from .context import Context
from .editor import Editor
from .transformer import Transformer
from .cell import Cell
import json
from .fromfile_manager import json_to_connections

def json_to_lib(ctx, data):
    pass

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

def json_to_cell(ctx, data, myname):
    dtype = data["dtype"]
    if isinstance(dtype, list):
        dtype = tuple(dtype)
    cell = Cell(dtype)
    if "data" in data:
        cell.set(data["data"])
    ctx._add_child(myname, cell)

def json_to_process(ctx, data, myname):
    if data["type"] == "editor":
        assert data["mode"] == "sync", data["mode"]
        params = data["params"]
        child = Editor(params)
    elif data["type"] == "transformer":
        assert data["mode"] == "thread", data["mode"]
        params = data["params"]
        child = Transformer(params)
    ctx._add_child(myname, child)
    """
    if isinstance(p, Editor):
        d["type"] = "editor"
        d["mode"] = "sync"
        d["params"] = p.editor_params
    elif isinstance(p, Transformer):
        d["type"] = "transformer"
        d["mode"] = "thread"
        d["params"] = p.transformer_params
    else:
        raise TypeError(p)
    if p._owner is not None:
        d["owner"] = sl_print(p._owner())
    return d
    """

def json_to_ctx(ctx, data, myname=None):

    if myname is None:
        myctx = ctx
    else:
        myctx = Context()

    myctx._like_process = data["like_process"]
    myctx._like_cell = data["like_cell"]
    #TODO: pins
    myctx._auto = set(data["auto"])
    for childname, c in data["children"].items():
        if "type" not in c:
            json_to_cell(myctx, c, childname)
        elif c["type"] in ("editor", "transformer"):
            json_to_process(myctx, c, childname)
        elif c["type"] == "context":
            json_to_ctx(myctx, c, childname)
    if myname is not None:
        ctx._add_child(myname, myctx)
    #TODO: owner

def fromfile(filename):
    import seamless
    data = json.load(open(filename))
    ctx = Context()
    json_to_lib(ctx, data["lib"])
    json_to_macro(ctx, data["macro"])
    json_to_ctx(ctx, data["main"])
    json_to_connections(ctx, data["main"])
    return ctx
