from .fromfile import find_sl

def json_to_connections(ctx, data):
    """
    ret = OrderedDict((
        #TODO ("macro_objects", macro_objects),
        #TODO ("macro_listeners", macro_listeners),
        #TODO ("registrar_items", registrar_items),
        #TODO ("registrar_listeners", registrar_listeners),
        #TODO ("registrar_cells", registrar_cells),
        ("pin_cell_connections", pin_cell_connections),
        ("cell_pin_connections", cell_pin_connections)
    ))
    """

    manager = ctx._manager
    for con in data["pin_cell_connections"]:
        source = find_sl(ctx, con[0])
        target = find_sl(ctx, con[1])
        try:
            manager.connect(source, target)
        except:
            print("SOURCE", source, "TARGET", target)
            raise
    for con in data["cell_pin_connections"]:
        source = find_sl(ctx, con[0])
        target = find_sl(ctx, con[1])
        try:
            manager.connect(source, target)
        except:
            print("SOURCE", source, "TARGET", target)
            raise
