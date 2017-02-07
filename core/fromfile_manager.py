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
    def _get_sl(parent, path):
        if len(path) == 0:
            return parent
        child = getattr(parent, path[0])
        return _get_sl(child, path[1:])

    def find_sl(path):
        path2 = path.split(".")
        return _get_sl(ctx, path2)

    manager = ctx._manager
    for con in data["pin_cell_connections"]:
        source = find_sl(con[0])
        target = find_sl(con[1])
        manager.connect(source, target)
    for con in data["cell_pin_connections"]:
        source = find_sl(con[0])
        target = find_sl(con[1])
        manager.connect(source, target)
