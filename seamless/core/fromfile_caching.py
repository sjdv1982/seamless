from contextlib import contextmanager


def _fromfile_caching_walk(ctx, clean_cells, transformers ):
    from .context import Context
    from .cell import Cell
    from .transformer import Transformer
    manager = ctx._manager
    all_cells = manager.cells
    for child in ctx._children.values():
        if isinstance(child, Context):
            _fromfile_caching_walk(child, clean_cells, transformers)
        elif isinstance(child, Transformer):
            transformers.add(child)
        elif isinstance(child, Cell) and child.resource is not None:
            r = child.resource
            dirty = False
            if r.dirty:
                dirty = True
            elif child.value is None:
                dirty = True
            if not dirty:
                c = manager.get_cell_id(child)
                if c in all_cells:
                    #print("CLEAN", child)
                    clean_cells.add(c)
            else:
                #print("NOT CLEAN", child, r.dirty, child.value is None)
                pass


def fromfile_caching(ctx):
    """This function is to be invoked right after a context has been loaded
    Sets as stable those transformers for which all cells (input and output)
     are clean.
    Clean cells fulfill the following conditions
    - Its value was saved, and no resource filepath has been defined
    - Its value was saved, and loading the resource file did not overwrite it
    - A hash of its value has been saved, and the resource file was loaded with the same hash
    Finally, macro objects that have only clean cells in their cell_args and their target
     are similarly stabilized
    """
    clean_cells, transformers = set(), set()
    _fromfile_caching_walk(ctx, clean_cells, transformers)

    manager = ctx._manager
    all_cells = manager.cells
    for tf in transformers:
        stable = True
        for pinname, pindict in tf.transformer_params.items():
            pin = getattr(tf, pinname)
            if pindict["pin"] == "output":
                for c in pin._cell_ids:
                    if c not in clean_cells:
                        stable = False
                        break
                if not stable:
                    break
            elif pindict["pin"] == "input":
                #c = pin.cell()
                curr_pin_to_cells = manager.pin_to_cells.get(pin.get_pin_id(), [])
                if len(curr_pin_to_cells) == 0:
                    continue
                assert len(curr_pin_to_cells) == 1
                c = curr_pin_to_cells[0]
                if c not in clean_cells:
                    #print("UNCLEAN", all_cells.get(c, None))
                    stable = False
                    break
        if stable:
            manager.set_stable(tf, True)
            tf.transformer.responsive = False
            tf.receive_update("@RESPONSIVE", None, None)

    for cell_id in manager.macro_listeners:
        if cell_id not in clean_cells:
            continue
        cell = manager.cells.get(cell_id, None)
        if cell is None:
            continue
        listeners = manager.macro_listeners[cell_id]
        for macro_object, macro_arg in listeners:
            for cell_arg_name in macro_object.cell_args:
                cell_arg = macro_object.cell_args[cell_arg_name]
                cell_arg_id = manager.get_cell_id(cell_arg)
                if cell_arg_id in clean_cells:
                    macro_object._last_cell_values[cell_arg_name] = cell_arg.value


@contextmanager
def fromfile_caching_ctx(ctx):
    yield
    fromfile_caching(ctx)
