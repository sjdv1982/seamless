def cache_signature_cell(cell, ctx_path, manager, known):
    from .transformer import Transformer
    from .reactor import Reactor
    if cell in known:
        return known[cell]
    known[cell] = cell.path #placeholder for infinite cycles
    sig = {}
    if cell.resource is None:
        return None
    cache = cell.resource.cache
    if cache is None and not cell.dependent:
        sig["mode"] = None
    elif cache == True or (cache is None and cell.dependent):
        sig["mode"] = "dependent"

        cell_id = manager.get_cell_id(cell)
        wsigs = []
        incons = manager.cell_to_output_pin.get(cell, [])
        pins = []
        for incon in incons:
            output_pin = incon()
            if output_pin is None:
                continue
            pins.append(output_pin)
        for pin in sorted(pins,key=lambda pin:pin.name):
            pinname = pin.name
            worker = pin.worker_ref()
            if worker.path[:len(ctx_path)] != ctx_path: #extern!
                continue
            if isinstance(worker, Transformer):
                wsig0 = cache_signature_transformer(worker, ctx_path, manager, known)
                wsig = (worker.path, ("transformer",pinname), wsig0)
            elif isinstance(worker, Reactor):
                wsig0 = cache_signature_reactor(worker, ctx_path, manager, known)
                wsig = (worker.path, ("reactor",pinname), wsig0)
            else:
                raise TypeError(worker)
            wsigs.append(wsig)

        aliases = manager.cell_aliases.get(cell_id, [])
        other_cells = []
        for other_cell_ref in aliases:
            other_cell = other_cell_ref()
            if other_cell is None:
                continue
            other_cells.append(other_cell)
        for other_cell in sorted(other_cells,key=lambda c:c.path):
            if other_cell.path[:len(ctx_path)] != ctx_path: #extern!
                continue
            else:
                wsig0 = cache_signature_cell(other_cell)
                wsig = (other_cell.path, "alias", wsig0)
            wsigs.append(wsig)

        if len(wsigs) == 0: #only extern connections
            sig["mode"] = None
        else:
            sig["signature"] = wsigs
    elif cache == False:
        sig["mode"] = "independent"
        hash_ = cell.resource.get_hash()
        sig["signature"] = hash_
    elif isinstance(cache, str):
        sig["mode"] = "fromfile"
        sig["signature"] = cache
    else:
        raise ValueError((cell, cache))
    known[cell] = sig
    return sig

def cache_signature_reactor(rc, ctx_path, manager, known):
    if rc in known:
        return known[rc]
    known[rc] = rc.path #placeholder for infinite cycles
    sig = {}
    manager = rc._get_manager()
    all_cells = manager.cells
    for pinname, pindict in rc.reactor_params.items():
        if pindict["pin"] == "output":
            continue
        pin = getattr(rc, pinname)
        #c = pin.cell()
        curr_pin_to_cells = manager.pin_to_cells.get(pin.get_pin_id(), [])
        if len(curr_pin_to_cells) == 0:
            continue
        assert len(curr_pin_to_cells) == 1
        c = curr_pin_to_cells[0]
        cell = all_cells[c] #should always exist (?)
        csig = cache_signature_cell(cell, ctx_path, manager, known)
        sig[pinname] = (pindict["pin"], pindict["dtype"], cell.path, csig)
    known[rc] = sig
    return sig

def cache_signature_transformer(tf, ctx_path, manager, known):
    if tf in known:
        return known[tf]
    known[tf] = tf.path #placeholder for infinite cycles
    sig = {}
    all_cells = manager.cells
    for pinname, pindict in tf.transformer_params.items():
        if pindict["pin"] == "output":
            continue
        pin = getattr(tf, pinname)
        #c = pin.cell()
        curr_pin_to_cells = manager.pin_to_cells.get(pin.get_pin_id(), [])
        if len(curr_pin_to_cells) == 0:
            continue
        assert len(curr_pin_to_cells) == 1
        c = curr_pin_to_cells[0]
        cell = all_cells[c] #should always exist
        csig = cache_signature_cell(cell, ctx_path, manager, known)
        sig[pinname] = (pindict["pin"], pindict["dtype"], cell.path, csig)
    known[tf] = sig
    return sig


def cache_signature(ctx, known=None):
    if known is None:
        known = {}
    if ctx in known:
        return known[ctx]

    known[ctx] = ctx.path #placeholder for infinite cycles

    from .context import Context
    from .cell import Cell
    from .transformer import Transformer
    from .reactor import Reactor

    if not isinstance(ctx, Context):
        raise TypeError(type(ctx))

    manager = ctx._manager
    ctx_path = tuple(ctx.path)
    signature = {}

    for childname, child in ctx._children.items():
        if isinstance(child, Context):
            signature[childname] = ("context", cache_signature(child, known))
        elif isinstance(child, Cell):
            sig = cache_signature_cell(child, ctx_path, manager, known)
            signature[childname] = ("cell", sig)
        elif isinstance(child, Transformer):
            sig = cache_signature_transformer(child, ctx_path, manager, known)
            signature[childname] = ("transformer", sig)
        elif isinstance(child, Reactor):
            sig = cache_signature_reactor(child, ctx_path, manager, known)
            signature[childname] = ("reactor", sig)
        else:
            raise TypeError(child)
    known[ctx] = signature
    return signature
