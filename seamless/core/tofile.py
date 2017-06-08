from collections import OrderedDict
import json, os
from .. import dtypes
from .reactor import Reactor
from .transformer import Transformer
from .worker import Worker
from .cell import Cell
from .context import Context

def sl_print(sl):
    sl = sl._find_successor()
    if sl is None:
        return None
    return ".".join(sl.path)
from .tofile_manager import manager_to_json

def worker_to_json(p):
    d = OrderedDict()
    if isinstance(p, Reactor):
        d["type"] = "reactor"
        d["mode"] = "sync"
        d["params"] = p.reactor_params
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
    result = OrderedDict((
        ("filepath", r.filepath),
        ("lib", r.lib),
        ("mode", r.mode),
    ))
    if r.save_policy > 0:
        result["save_policy"] = r.save_policy
    return result

def cell_to_json(c):
    c = c._find_successor()
    d = OrderedDict()
    store_data = True
    store_hash = False
    if c._dependent:
        store_data = False
    d["dtype"] = c.dtype
    if c.dtype is None:
        d["dtype"] = "signal"
    if c.resource is not None:
        if c.resource.filepath is not None or c.resource.save_policy is not None:
            d["resource"] = resource_to_json(c.resource)
            if c.resource.mode == 1:
                store_data = False

        sp = c.resource.save_policy
        if sp == 0:
            pass
        elif sp == 1:
            pass
        elif sp == 2: #TODO: MAX_SAVE bytes
            if c.resource.filepath is None or c.resource.mode == 1:
                store_data = True
        elif sp == 3:
            if c.resource.filepath is None or c.resource.mode == 1:
                store_data = True
        elif sp == 4:
            store_data = True
        if sp > 0:
            if not store_data:
                store_hash = True
    if store_data and c.dtype == "array":
        raise NotImplementedError("Saving array cell data is not (yet?) supported")

    if c._preliminary:
        store_data = False
        store_hash = False

    if store_data and c.data is not None:
        data = c.data
        is_json = (
          c.dtype == "json" or (
            isinstance(c.dtype, tuple) and c.dtype[0] == "json"
          )
        )
        if not is_json:
            data = dtypes.serialize(c.dtype, data)
        d["data"] = data
    if store_hash and c.data is not None:
        hash_ = c.resource.get_hash()
        d["hash"] = hash_
    if c._owner is not None:
        d["owner"] = sl_print(c._owner())
    if c.dtype == "array":
        if c._store is not None:
            d["store"] = {
              "mode": c._store_mode,
              "params": c._store.init_params
            }
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
    children = {}
    d = OrderedDict((
        ("type", "context"),
        ("like_worker", ctx._like_worker),
        ("like_cell", ctx._like_cell),
        ("pins", {pname: (p.__class__.__name__, sl_print(p)) for pname, p in ctx._pins.items()}),
        ("auto", [a for a in sorted(ctx._auto) if a in ctx._children]),
        ("children", children),
    ))
    for childname, child in ctx._children.items():
        if isinstance(child, Context):
            dd = ctx_to_json(child)
        elif isinstance(child, Cell):
            dd = cell_to_json(child)
        elif isinstance(child, Worker):
            dd = worker_to_json(child)
        elif isinstance(child, RegistrarObject):
            dd = registrar_object_to_json(child)
        else:
            raise TypeError((str(child), type(child)))
        children[childname] = dd
        try:
            json.dumps(dd)
        except Exception as e:
            raise Exception((e, childname, child))
    json.dumps(d)
    if ctx.context is None or ctx._manager is not ctx.context._manager:
        dd = manager_to_json(ctx._manager)
        json.dumps(dd)
        d.update(dd)
    if ctx._owner is not None:
        d["owner"] = sl_print(ctx._owner())
    json.dumps(d)
    return d

def lib_to_json():
    from .libmanager import _lib, _links
    ret = {}
    for filename in _lib:
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
        if macro.with_caching:
            m["with_caching"] = True
        m["dtype"] = macro.dtype
        #m["type_args"] = macro._type_args_unparsed
        m["type_args"] = macro._type_args_processed
        m["module_name"] = module_name
        m["func_name"] = func_name
        m["code"] = macro.code
        ret.append(m)
    return ret

from .utils import ordered_dictsort

def tofile(ctx, filename, backup=True):
    assert isinstance(ctx, Context)
    if ctx.context is not None:
        raise NotImplementedError(".tofile for non-root contexts not supported")
    data = OrderedDict((
      ("lib" , lib_to_json()),
      ("macro" , macro_to_json()),
      ("main" , ctx_to_json(ctx)),
    ))
    ordered_dictsort(data)
    #import pprint
    #pprint.pprint(  data, open(filename, "w"))
    json.dumps(data["lib"])
    json.dumps(data["macro"])
    json.dumps(data["main"])
    jdata = json.dumps(data, indent=2)
    if backup and os.path.exists(filename):
        count = 1
        while 1:
            new_filename = filename + str(count)
            if not os.path.exists(new_filename):
                break
            count += 1
        os.rename(filename, new_filename)
    open(filename, "w").write(jdata)
