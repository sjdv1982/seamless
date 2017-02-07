from collections import OrderedDict
from .tofile import sl_print

def macro_object_to_json(macro_object):
    """Serializes a MacroObject
    """
    from .registrar import RegistrarObject
    target = macro_object._parent()
    if macro_object.macro.registrar is not None:
        assert isinstance(target, RegistrarObject)
        #MacroObjects that point to a registrar are saved as registrar_cell`
        # instead
        return None
    else:
        assert not isinstance(target, RegistrarObject)

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
            cell_args[argname] = sl_print(arg)
            args.pop(argname)
        else:
            pass #TODO: check that arg is serialisable
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
    mo["target"] = sl_print(target)
    return mo

def manager_to_json(m):
    from .process import Process
    from .macro import MacroObject
    macro_objects = []
    macro_listeners = []
    registrar_items = []
    registrar_listeners = []
    registrar_cells = []
    pin_cell_connections = []
    cell_pin_connections = []
    ret = OrderedDict((
        ("macro_objects", macro_objects),
        ("macro_listeners", macro_listeners),
        ("registrar_items", registrar_items),
        ("registrar_listeners", registrar_listeners),
        ("registrar_cells", registrar_cells),
        ("pin_cell_connections", pin_cell_connections),
        ("cell_pin_connections", cell_pin_connections)
    ))

    for cell, pins in m.cell_to_output_pin.items():
        cpath = sl_print(cell)
        for pin0 in pins:
            pin = pin0()
            if pin is None:
                continue
            ppath = sl_print(pin)
            pin_cell_connections.append((ppath, cpath))

    for cell_id, pins in m.listeners.items():
        cell = m.cells[cell_id]
        cpath = sl_print(cell)
        for pin0 in pins:
            pin = pin0()
            if pin is None:
                continue
            ppath = sl_print(pin)
            cell_pin_connections.append((cpath, ppath))

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
                mo = macro_obj_map[macro_object]
            else:
                mo = macro_object_to_json(macro_object)
                macro_obj_map[macro_object] = mo
                if mo is not None:
                    macro_objects.append(mo)
            i = OrderedDict()
            i["cell"] = sl_print(cell)
            i["macro_target"] = sl_print(macro_object._parent())
            if mo is not None:
                i["macro_arg"] = macro_arg
                macro_listeners.append(i)
            else:
                i["registrar"] = macro_object.macro.registrar.name
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
                    i["target_process"] = sl_print(target)
                    namespace_name = t[1]
                    i["namespace_name"] = t[1]
                    target.receive_registrar_update(registrar.name, key, namespace_name)
                elif isinstance(target, MacroObject):
                    macro_object = target
                    assert macro_object.macro.registrar is None #registrars can't target other registrars
                    i["target_type"] = "macro_object"
                    if macro_object in macro_obj_map:
                        mo = macro_obj_map[macro_object]
                    else:
                        mo = macro_object_to_json(macro_object)
                        macro_obj_map[macro_object] = mo
                        macro_objects.append(mo)
                    i["target_macro_target"] = mo["target"]
                registrar_listeners.append(i)
    return ret
