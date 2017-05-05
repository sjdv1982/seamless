def find_external_connections_cell(external_connections, cell, path, parent_path, parent_owns):
    owns = parent_owns
    if owns is None:
        owns = cell._owns_all()
    manager = cell._get_manager()
    cell_id = manager.get_cell_id(cell)
     #no macro listeners or registrar listeners; these the macro should re-create
    incons = manager.cell_to_output_pin.get(cell, [])
    for incon in incons:
        output_pin = incon()
        if output_pin is None:
            continue
        worker = output_pin.worker_ref()
        if worker is None or worker in owns:
            continue
        if parent_path is not None:
            if output_pin.path[:len(parent_path)] == parent_path:
                continue
        external_connections.append(("input", output_pin, path, output_pin.path))
    outcons = manager.listeners.get(cell_id, [])
    for outcon in outcons:
        input_pin = outcon()
        if input_pin is None:
            continue
        worker = input_pin.worker_ref()
        if worker is None or worker in owns:
            continue
        if parent_path is not None:
            if input_pin.path[:len(parent_path)] == parent_path:
                continue
        assert len(input_pin.path)
        external_connections.append(("output", path, input_pin, input_pin.path))
    aliases = manager.cell_aliases.get(cell_id, [])
    for other_cell_ref in aliases:
        other_cell = other_cell_ref()
        if other_cell is None:
            continue
        if other_cell.path[:len(parent_path)] == parent_path:
            continue
        external_connections.append(("alias", path, other_cell, other_cell.path))
    rev_aliases = manager.cell_rev_aliases.get(cell_id, [])
    for other_cell_ref in rev_aliases:
        other_cell = other_cell_ref()
        if other_cell is None:
            continue
        if other_cell.path[:len(parent_path)] == parent_path:
            continue
        external_connections.append(("rev_alias", other_cell, path, other_cell.path))

def find_external_connections_worker(external_connections, worker, path, parent_path, parent_owns):
    from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase
    if path is None:
        path = ()
    owns = parent_owns
    if owns is None:
        owns = worker._owns_all()
    for pinname, pin in worker._pins.items():
        manager = pin._get_manager()
        pin_id = pin.get_pin_id()
        if isinstance(pin, (InputPinBase, EditPinBase)):
            is_incoming = True
            cell_ids = [(None, v) for v in manager.pin_to_cells.get(pin_id, [])]
        elif isinstance(pin, OutputPinBase):
            is_incoming = False
            cell_ids = [(None, v) for v in pin._cell_ids]
        else:
            raise TypeError((pinname, pin))
        for subpin, cell_id in cell_ids:
            cell = manager.cells.get(cell_id, None)
            if cell is None:
                continue
            if cell in owns:
                continue
            if parent_path is not None:
                if cell.path[:len(parent_path)] == parent_path:
                    continue
            path2 = path + (pinname,)
            if subpin is not None:
                path2 += (subpin,)
            if is_incoming:
                external_connections.append(("input", cell, path2, cell.path))
            else:
                external_connections.append(("output", path2, cell, cell.path))

def find_external_connections(external_connections, ctx, path, parent_path, parent_owns):
    from .context import Context
    from .cell import Cell
    from .worker import Worker
    parent_path2 = parent_path
    if parent_path is None:
        parent_path2 = ctx.path
    owns = parent_owns
    if owns is None:
        owns = ctx._owns_all()
    for childname, child in ctx._children.items():
        if path is not None:
            path2 = path + (childname,)
        else:
            path2 = (childname,)
        if isinstance(child, Cell):
            find_external_connections_cell(external_connections, child, path2, parent_path2, owns)
        elif isinstance(child, Worker):
            find_external_connections_worker(external_connections, child, path2, parent_path2, owns)
        elif isinstance(child, Context):
            find_external_connections(external_connections,child, path2, parent_path2, owns)
        else:
            raise TypeError((childname, child))

def find_internal_connections_cell(internal_connections, cell, path, parent_path):
    assert parent_path is not None
    manager = cell._get_manager()
    cell_id = manager.get_cell_id(cell)
    #no macro listeners or registrar listeners; TODO, or not???

    incons = manager.cell_to_output_pin.get(cell, [])
    for incon in incons:
        output_pin = incon()
        if output_pin is None:
            continue
        worker = output_pin.worker_ref()
        if worker is None:
            continue
        if output_pin.path[:len(parent_path)] != parent_path:
            continue
        output_path = output_pin.path[len(parent_path):]
        internal_connections.append((output_path, path))

    outcons = manager.listeners.get(cell_id, [])
    for outcon in outcons:
        input_pin = outcon()
        if input_pin is None:
            continue
        worker = input_pin.worker_ref()
        if worker is None:
            continue
        if input_pin.path[:len(parent_path)] != parent_path:
            continue
        assert len(input_pin.path)
        input_path = input_pin.path[len(parent_path):]
        internal_connections.append((path, input_path))

    aliases = manager.cell_aliases.get(cell_id, [])
    for other_cell_ref in aliases:
        other_cell = other_cell_ref()
        if other_cell is None:
            continue
        if other_cell.path[:len(parent_path)] != parent_path:
            continue
        other_path = other_cell.path[len(parent_path):]
        internal_connections.append((path, other_path))
    #aliases cover for rev_aliases, since both are internal in internal connections

def find_internal_connections_worker(internal_connections, worker, path, parent_path):
    return #all internal connections should have been found at the cell level...
    """
    from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase
    assert parent_path is not None
    if path is None:
        path = ()
    for pinname, pin in worker._pins.items():
        manager = pin._get_manager()
        pin_id = pin.get_pin_id()
        if isinstance(pin, (InputPinBase, EditPinBase)):
            is_incoming = True
            cell_ids = [(None, v) for v in manager.pin_to_cells.get(pin_id, [])]
        elif isinstance(pin, OutputPinBase):
            is_incoming = False
            cell_ids = [(None, v) for v in pin._cell_ids]
        else:
            raise TypeError((pinname, pin))
        for subpin, cell_id in cell_ids:
            cell = manager.cells.get(cell_id, None)
            if cell is None:
                continue
            if cell.path[:len(parent_path)] != parent_path:
                continue
            path2 = path + (pinname,)
            if subpin is not None:
                path2 += (subpin,)
            if is_incoming:
                #external_connections.append(("input", cell, path2, cell.path))
            else:
                #external_connections.append(("output", path2, cell, cell.path))
    """

def find_internal_connections(internal_connections, ctx, path, parent_path):
    from .context import Context
    from .cell import Cell
    from .worker import Worker
    parent_path2 = parent_path
    if parent_path is None:
        parent_path2 = ctx.path
    for childname, child in ctx._children.items():
        if path is not None:
            path2 = path + (childname,)
        else:
            path2 = (childname,)
        if isinstance(child, Cell):
            find_internal_connections_cell(internal_connections, child, path2, parent_path2)
        elif isinstance(child, Worker):
            find_internal_connections_worker(internal_connections, child, path2, parent_path2)
        elif isinstance(child, Context):
            find_internal_connections(internal_connections,child, path2, parent_path2)
        else:
            raise TypeError((childname, child))
