from collections import OrderedDict
import json
from .. import dtypes
from .editor import Editor
from .transformer import Transformer
from .process import Process
from .cell import Cell
from .context import Context

def sl_print(sl):
    return ".".join(sl.path)
from .tofile_manager import manager_to_json

def process_to_json(p):
    d = OrderedDict()
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

def resource_to_json(r):
    return OrderedDict((
        ("filename", r.filename),
        ("lib", r.lib),
        ("mode", r.mode),
    ))

def cell_to_json(c):
    d = OrderedDict()
    store_data = True
    if c._dependent:
        store_data = False
    d["dtype"] = c.dtype
    if c.resource.filename is not None:
        d["resource"] = resource_to_json(c.resource)
        if c.resource.lib or c.resource.mode == 1:
            store_data = False
    if store_data and c.data is not None:
        data = dtypes.serialize(c.dtype, c.data)
        d["data"] = data
    if c._owner is not None:
        d["owner"] = sl_print(c._owner())
    return d

def registrar_object_to_json(ro):
    d = OrderedDict()
    d["registrar"] = ro.registrar.name
    d["registered"] = ro.registered #TODO: check if serialisable
    d["data"] = ro.data
    d["data_name"] = ro.data_name
    return d

def ctx_to_json(ctx):
    ctx._cleanup_auto()

    from .registrar import RegistrarObject
    children = OrderedDict()
    d = OrderedDict((
        ("type", "context"),
        ("like_process", ctx._like_process),
        ("like_cell", ctx._like_cell),
        ("pins", OrderedDict([(pname, sl_print(p)) for pname, p in sorted(ctx._pins.items())])),
        ("auto", [a for a in sorted(ctx._auto) if a in ctx._children]),
        ("children", children),
    ))
    for childname, child in sorted(ctx._children.items()):
        if isinstance(child, Context):
            children[childname] = ctx_to_json(child)
        elif isinstance(child, Cell):
            children[childname] = cell_to_json(child)
        elif isinstance(child, Process):
            children[childname] = process_to_json(child)
        elif isinstance(child, RegistrarObject):
            children[childname] = registrar_object_to_json(child)
        else:
            raise TypeError((str(child), type(child)))
    if ctx.context is None or ctx._manager is not ctx.context._manager:
        d.update(manager_to_json(ctx._manager))
    if ctx._owner is not None:
        d["owner"] = sl_print(ctx._owner())
    return d

def lib_to_json():
    from .libmanager import _lib, _links
    ret = OrderedDict()
    for filename in sorted(_lib.keys()):
        data = _lib[filename]
        links = [sl_print(cell) for cell in _links.get(filename,[])]
        ret[filename] = OrderedDict((("data", data), ("links", links)))
    return ret

def macro_to_json():
    from .macro import _macros
    ret = []
    for module_name, func_name in sorted(_macros.keys()):
        macro = _macros[module_name, func_name]
        if macro.registrar is not None:
            continue #registrar register methods are never saved
        m = OrderedDict()
        m["with_context"] = macro.with_context
        m["dtype"] = macro.dtype
        m["type_args"] = macro._type_args_unparsed
        m["module_name"] = module_name
        m["func_name"] = func_name
        m["code"] = macro.code
        ret.append(m)
    return ret

def tofile(ctx, filename):
    assert isinstance(ctx, Context)
    if ctx.context is not None:
        raise NotImplementedError(".tofile for non-root contexts not supported")
    data = OrderedDict((
      ("lib" , lib_to_json()),
      ("macro" , macro_to_json()),
      ("main" , ctx_to_json(ctx)),
    ))
    #import pprint
    #pprint.pprint(  data, open(filename, "w"))
    json.dump(data, open(filename, "w"), indent=2)
