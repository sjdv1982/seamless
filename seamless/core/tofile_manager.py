from collections import OrderedDict
from .tofile import sl_print
import json

def macro_object_to_json(macro_object):
    """Serializes a MacroObject
    """
    from .registrar import RegistrarObject
    target = macro_object._parent()
    if macro_object.macro.registrar is not None:
        assert isinstance(target, RegistrarObject), (str(target), macro_object.macro.registrar)
        #MacroObjects that point to a registrar are saved as registrar_cell
        # instead
        return None
    else:
        assert not isinstance(target, RegistrarObject)

    if target is None or sl_print(target) is None:
        print("WARNING: macro object points to a dead cell, not saved!")
        return None

    mo = OrderedDict()
    macro = macro_object.macro
    order = macro._type_args["_order"]

    args = []
    kwargs = {}
    cell_args = {}
    for argnr, arg in enumerate(macro_object.args):
        if argnr in macro_object.cell_args:
            cell_args[argnr] = sl_print(arg)
            args.append(None)
        else:
            json.dumps(arg)
            args.append(arg)
    for argname, arg in macro_object.kwargs.items():
        if argname in macro_object.cell_args:
            cell_args[argname] = sl_print(arg)
        else:
            json.dumps(arg)
            kwargs[argname] = arg
    mo["args"] = args
    mo["kwargs"] = kwargs
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
    json.dumps(mo)
    return mo

def manager_to_json(m):
    from .worker import Worker
    from .macro import MacroObject
    macro_objects = []
    macro_listeners = []
    registrar_items = []
    registrar_listeners = []
    registrar_cells = []
    pin_cell_connections = []
    cell_pin_connections = []
    cell_cell_connections = []
    ret = OrderedDict((
        ("macro_objects", macro_objects),
        ("macro_listeners", macro_listeners),
        ("registrar_items", registrar_items),
        ("registrar_listeners", registrar_listeners),
        ("registrar_cells", registrar_cells),
        ("pin_cell_connections", pin_cell_connections),
        ("cell_pin_connections", cell_pin_connections),
        ("cell_cell_connections", cell_cell_connections)

    ))

    for cell, pins in m.cell_to_output_pin.items():
        cpath = sl_print(cell)
        for pin0 in pins:
            pin = pin0()
            if pin is None:
                continue
            ppath = sl_print(pin)
            if ppath is None or cpath is None:
                m1 = cell.format_path()
                if cpath is None:
                    m1 += " (dead)"
                m2 = pin.format_path()
                if ppath is None:
                    m2 += " (dead)"
                print("WARNING: dead connection, not saved: '%s' to '%s'" % (m2, m1))
                continue
            pin_cell_connections.append((ppath, cpath))
    pin_cell_connections.sort(key=lambda v: v[0]+v[1])
    json.dumps(pin_cell_connections)

    for cell_id, pins in m.listeners.items():
        ppaths = []
        for pin0 in pins:
            pin = pin0()
            if pin is None:
                continue
            ppath = sl_print(pin)
            ppaths.append(ppath)

        try:
            cell = m.cells[cell_id]
        except KeyError:
            print("WARNING: lost cell connecting to pins {0}".format(ppaths))
            continue
        cpath = sl_print(cell)
        for ppath in ppaths:
            cell_pin_connections.append((cpath, ppath))
    cell_pin_connections.sort(key=lambda v: v[0]+v[1])
    json.dumps(cell_pin_connections)

    for cell_id, aliases in m.cell_aliases.items():
        apaths = []
        for alias0 in aliases:
            alias = alias0()
            if alias is None:
                continue
            apath = sl_print(alias)
            apaths.append(apath)
        try:
            cell = m.cells[cell_id]
        except KeyError:
            print("WARNING: lost cell connecting to cell {0}".format(apaths))
            continue
        cpath = sl_print(cell)
        for apath in apaths:
            cell_cell_connections.append((cpath, apath))
    cell_cell_connections.sort(key=lambda v: v[0]+v[1])
    json.dumps(cell_cell_connections)

    macro_obj_map = {}
    for cell_id in m.macro_listeners:
        cell = m.cells.get(cell_id, None)
        if cell is None:
            continue
        listeners = m.macro_listeners[cell_id]
        for macro_object, macro_arg in listeners:
            if macro_object is None:
                continue
            if macro_object in macro_obj_map:
                mo = macro_obj_map[macro_object]
            else:
                mo = macro_object_to_json(macro_object)
                macro_obj_map[macro_object] = mo
                if mo is not None:
                    json.dumps(mo)
                    macro_objects.append(mo)
            macro_target = macro_object._parent()
            if macro_target is None:
                print("WARNING: dead macro object target (%s), not saved!" % cell)
                continue
            i = OrderedDict()
            i["cell"] = sl_print(cell)
            i["macro_target"] = sl_print(macro_target)
            if mo is not None:
                i["macro_arg"] = macro_arg
                json.dumps(i)
                macro_listeners.append(i)
            else:
                i["registrar"] = macro_object.macro.registrar.name
                json.dumps(i)
                registrar_cells.append(i)

    for registrar_name, dtype, data, data_name in m.registrar_items:
        i = OrderedDict()
        assert isinstance(registrar_name, str)
        i["registrar_name"] = registrar_name
        i["dtype"] = dtype
        i["data"] = data #TODO: check that it is already serialized?
        i["data_name"] = data_name
        json.dumps(i)
        registrar_items.append(i)

    for registrar in sorted(m.registrar_listeners.keys(),
      key=lambda k: k.name):
        d = m.registrar_listeners[registrar]
        for key in sorted(d):
            for t in d[key]:
                target = t[0]()
                if target is None:
                    continue
                i = OrderedDict()
                i["registrar"] = registrar.name
                i["key"] = key
                if isinstance(target, Worker):
                    i["target_type"] = "worker"
                    i["target_worker"] = sl_print(target)
                    namespace_name = t[1]
                    i["namespace_name"] = t[1]
                    #target.receive_registrar_update(registrar.name, key, namespace_name)
                elif isinstance(target, MacroObject):
                    macro_object = target
                    assert macro_object.macro.registrar is None #registrars can't target other registrars
                    i["target_type"] = "macro_object"
                    if macro_object in macro_obj_map:
                        mo = macro_obj_map[macro_object]
                    else:
                        mo = macro_object_to_json(macro_object)
                        macro_obj_map[macro_object] = mo
                        json.dumps(mo)
                        macro_objects.append(mo)
                    i["target_macro_target"] = mo["target"]
                json.dumps(i)
                registrar_listeners.append(i)
    return ret
