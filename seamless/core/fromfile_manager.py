from .fromfile import find_sl

def json_to_registrar_items(ctx, m, data):
    for i in data["registrar_items"]:
        registrar_name = i["registrar_name"]
        dtype = tuple(i["dtype"])
        data = i["data"]
        data_name = i["data_name"]
        #m.add_registrar_item(registrar_name, dtype, data, data_name) #auto triggered
        registrar = getattr(ctx.registrar, registrar_name)
        registrar.register(data) #TODO: data_name?

def json_to_macro_objects(ctx, data):
    from .macro_object import MacroObject
    from .macro import _macros
    macro_objects = {}
    ret = {}
    manager = ctx._manager
    for d in data:
        key = (d["macro_module_name"], d["macro_func_name"])
        macro = _macros[key]
        order = macro._type_args["_order"]
        args = []
        for argname, arg in enumerate(d["args"]):
            args.append(arg)
        kwargs = {}
        for argname, arg in d["kwargs"].items():
            kwargs[argname] = arg
        cell_args = {}
        for argname, arg0 in d["cell_args"].items():
            arg = find_sl(ctx, arg0)
            try:
                argname = int(argname)
                is_int = True
            except ValueError:
                is_int = False
            if is_int:
                for n in range(len(args), argname+1):
                    args.append(None)
                args[argname] = arg
            else:
                kwargs[argname] = arg
            cell_args[argname] = arg
        if key not in macro_objects:
            macro_objects[key] = []
        mo = (
            d["macro_order"],
            args,
            kwargs,
            cell_args,
            d["target"]
        )
        macro_objects[key].append(mo)

    macro_objects2 = []
    for key in sorted(macro_objects.keys()):
        macro = _macros[key]
        m_objects = sorted(macro_objects[key], key=lambda v:v[0])
        for _, args, kwargs, cell_args, target0 in m_objects:
            macro_object = MacroObject(macro, args, kwargs, cell_args)
            target = find_sl(ctx, target0)
            macro_objects2.append((macro_object, target))
            ret[target0] = macro_object
    for macro_object, target in macro_objects2:
        macro_object.connect(target) #adds the macro object to the manager too
    return ret

def json_to_macro_listeners(ctx, data, macro_objects):
    """
    m = ctx._manager
    for i in data:
        cell = find_sl(ctx, i["cell"])
        macro_object = macro_objects["macro_target"])
        macro_arg = i["macro_arg"]
        m.add_macro_listener(cell, macro_object, macro_arg)
    """
    pass #redundant: macro object.connect(target) creates the listener

def json_to_registrar_cells(ctx, data):
    from .macro import _macros, Macro
    from .registrar import RegistrarObject
    from .macro_object import MacroObject
    m = ctx._manager
    for i in data:
        cell = find_sl(ctx, i["cell"])
        registrar_object = find_sl(ctx, i["macro_target"])
        assert isinstance(registrar_object, RegistrarObject)
        registrar_name = i["registrar"]
        registrar_macro = getattr(ctx.registrar, registrar_name).register
        mo = MacroObject(registrar_macro, [None, cell], {}, {'_arg1': cell})
        mo.connect(registrar_object)
        # Redundant: mo.connect creates the listener
        #macro_arg = i["macro_arg"]
        #m.add_macro_listener(cell, macro_object, macro_arg)

def json_to_registrar_listeners(ctx, data, macro_objects):
    m = ctx._manager
    for i in data:
        registrar = getattr(ctx.registrar, i["registrar"])._registrar
        key = i["key"]
        if i["target_type"] == "worker":
            target = find_sl(ctx, i["target_worker"])
            namespace_name = i["namespace_name"]
        elif i["target_type"] == "macro_object":
            target = macro_objects[i["target_macro_target"]]
            namespace_name = None
        m.add_registrar_listener(registrar, key, target, namespace_name)
        if i["target_type"] == "worker":
            target.receive_registrar_update(registrar.name, key, namespace_name)

def json_to_connections(ctx, data):
    manager = ctx._manager
    for con in data["pin_cell_connections"]:
        source = find_sl(ctx, con[0])
        target = find_sl(ctx, con[1])
        try:
            manager.connect(source, target)
        except Exception:
            print("SOURCE", source, "TARGET", target)
            raise
    for con in data["cell_pin_connections"] + \
      data.get("cell_cell_connections",[]):
        source = find_sl(ctx, con[0])
        target = find_sl(ctx, con[1])
        try:
            manager.connect(source, target)
        except Exception:
            print("SOURCE", source, "TARGET", target)
            raise
