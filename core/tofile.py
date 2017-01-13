#TODO: cell-pin-cell connections!
#registrar_listeners is empty for fireworks.py

from collections import OrderedDict
import json
from .. import dtypes
from .editor import Editor
from .transformer import Transformer
from .process import Process
from .cell import Cell
from .context import Context

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
        d["owner"] = list(p._owner().path)
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
    if c.resource.filename is not None:
        d["resource"] = resource_to_json(c.resource)
        if c.resource.lib or c.resource.mode == 1:
            store_data = False
    if store_data:
        data = dtypes.serialize(c.dtype, c.data)
        d["data"] = data
    if c._owner is not None:
        d["owner"] = list(c._owner().path)
    return d

def macro_object_to_json(macro_object):
    from .registrar import RegistrarObject
    mo = OrderedDict()
    macro = macro_object.macro
    order = macro.type_args["_order"]

    args = OrderedDict()
    cell_args = OrderedDict()
    args.update(macro_object.kwargs)
    for argnr, arg in enumerate(macro_object.args):
        argname = order[argnr]
        args[argname] = arg
    for argname, arg in list(args.items()):
        if argname in macro_object.cell_args:
            cell_args[argname] = arg.path
            args.pop(argname)
        else:
            pass #TODO: check that arg is serialisable
    if macro_object.macro.registrar is not None and "_arg1" in args:
        args.pop("_arg1")
    mo["args"] = args
    mo["cell_args"] = cell_args

    for order,k in enumerate(sorted(macro.macro_objects.keys())):
        if macro.macro_objects[k] is not macro_object:
            continue
        break
    else:
        raise Exception("Disconnected macro object")
    mo["macro_module_name"] = macro.module_name
    mo["macro_func_name"] = macro.func_name
    mo["macro_order"] = order
    target = macro_object._parent()
    if macro_object.macro.registrar is not None:
        assert isinstance(target, RegistrarObject)
    else:
        assert not isinstance(target, RegistrarObject)
    mo["target"] = target.path
    return mo

def manager_to_json(m):
    from .process import Process
    from .macro import MacroObject
    macro_objects = []
    macro_listeners = []
    registrar_items = []
    registrar_listeners = []
    registrar_cells = []
    connections = []
    ret = OrderedDict((
        ("macro_objects", macro_objects),
        ("macro_listeners", macro_listeners),
        ("registrar_items", registrar_items),
        ("registrar_listeners", registrar_listeners),
        ("registrar_cells", registrar_cells),
        ("connections", connections)
    ))
    macro_obj_map = {}
    for cell_id in m.macro_listeners:
        cell = m.cells.get(cell_id, None)
        if cell is None:
            continue
        listeners = m.macro_listeners[cell_id]
        for macro_ref, macro_arg in listeners:
            macro_object = macro_ref()
            if macro_object is None:
                continue
            if macro_object in macro_obj_map:
                registrar_handle, mo = macro_obj_map[macro_object]
            else:
                mo = macro_object_to_json(macro_object)
                registrar_handle = macro_object.macro.registrar
                macro_obj_map[macro_object] = registrar_handle, mo
                macro_objects.append(mo)
            i = OrderedDict()
            i["cell"] = cell.path
            i["macro_target"] = mo["target"]
            if registrar_handle is None:
                i["macro_arg"] = macro_arg
                macro_listeners.append(i)
            else:
                i["registrar"] = registrar_handle.name
                registrar_cells.append(i)

    for registrar_name, dtype, data, data_name in m.registrar_items:
        i = OrderedDict()
        assert isinstance(registrar_name, str)
        i["registrar_name"] = registrar_name
        i["dtype"] = dtype
        i["data"] = data #TODO: check that it is already serialized?
        i["data_name"] = data_name
        registrar_items.append(i)
    for registrar in m. registrar_listeners:
        d = m.registrar_listeners[registrar]
        for key in d:
            for t in d[key]:
                target = t[0]()
                if target is None:
                    continue
                i = OrderedDict()
                i["registrar"] = registrar.name
                i["key"] = key
                if isinstance(target, Process):
                    i["target_type"] = "process"
                    i["target_process"] = target.path
                    namespace_name = t[1]
                    i["namespace_name"] = t[1]
                    target.receive_registrar_update(registrar.name, key, namespace_name)
                elif isinstance(target, MacroObject):
                    i["type"] = "macro_object"
                    if macro_object in macro_obj_map:
                        registrar_handle, mo = macro_obj_map[macro_object]
                    else:
                        mo = macro_object_to_json(macro_object)
                        registrar_handle = macro_object.macro.registrar
                        macro_obj_map[macro_object] = registrar_handle, mo
                        macro_objects.append(mo)
                    assert registrar_handle is None #registrars can't target other registrars
                    i["target_macro_target"] = mo["target"]
    return ret

def registrar_object_to_json(ro):
    d = OrderedDict()
    d["registrar"] = ro.registrar.name
    d["registered"] = ro.registered #TODO: check if serialisable
    #d["data"] = ro.data #not needed; data_name can be used to retrieve the registrar_item
    d["data_name"] = ro.data_name
    return d

def ctx_to_json(ctx):
    from .registrar import RegistrarObject
    children = OrderedDict()
    d = OrderedDict((
        ("like_process", ctx._like_process),
        ("like_cell", ctx._like_cell),
        ("pins", OrderedDict([(pname, p.path) for pname, p in sorted(ctx._pins.items())])),
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
        d["owner"] = list(ctx._owner().path)
    return d

def lib_to_json():
    from .libmanager import _lib, _links
    ret = OrderedDict()
    for filename in sorted(_lib.keys()):
        data = _lib[filename]
        links = [cell.path for cell in _links.get(filename,[])]
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
        m["dtype"] = macro.dtype
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
