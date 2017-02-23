import weakref

class MacroObject:
    macro = None
    args = []
    kwargs = {}
    cell_args = {}
    _parent = None

    def __init__(self, macro, args, kwargs, cell_args):
        self.macro = macro
        self.args = args
        self.kwargs = kwargs
        self.cell_args = weakref.WeakValueDictionary(cell_args)
        max_key = 0
        mo = macro.macro_objects
        if len(mo):
            max_key = max(mo.keys())
        mo[max_key+1] = self

    def connect(self, parent):
        from .cell import CellLike
        from .process import ProcessLike
        from .registrar import RegistrarObject
        assert (isinstance(parent, CellLike) and parent._like_cell) or \
         (isinstance(parent, ProcessLike) and parent._like_process) or \
         isinstance(parent, RegistrarObject), type(parent)
        #TODO: check that all cells and parent share a common root
        self._parent = weakref.ref(parent)
        for k in self.cell_args:
            cell = self.cell_args[k]
            cell.add_macro_object(self, k)

    def update_cell(self, cellname):
        from .context import Context
        from .cell import Cell
        from .process import Process, InputPinBase, OutputPinBase, EditPinBase
        parent = self._parent()
        grandparent = parent.context
        assert isinstance(grandparent, Context), grandparent
        for parent_childname in grandparent._children:
            if grandparent._children[parent_childname] is parent:
                break
        else:
            exc = "Cannot identify parent-child relationship of macro context {0}"
            raise AttributeError(exc.format(parent))
        external_connections = []

        def find_external_connections_cell(cell, path, parent_path, parent_owns):
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
                process = output_pin.process_ref()
                if process is None or process in owns:
                    continue
                if parent_path is not None:
                    if output_pin.path[:len(parent_path)] == parent_path:
                        continue
                external_connections.append((True, output_pin, path, output_pin.path))
            outcons = manager.listeners[cell_id]
            for outcon in outcons:
                input_pin = outcon()
                if input_pin is None:
                    continue
                process = input_pin.process_ref()
                if process is None or process in owns:
                    continue
                if parent_path is not None:
                    if input_pin.path[:len(parent_path)] == parent_path:
                        continue
                assert len(input_pin.path)
                external_connections.append((False, path, input_pin, input_pin.path))

        def find_external_connections_process(process, path, parent_path, parent_owns):
            if path is None:
                path = ()
            owns = parent_owns
            if owns is None:
                owns = process._owns_all()
            for pinname, pin in process._pins.items():
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
                        external_connections.append((True, cell, path2, cell.path))
                    else:
                        external_connections.append((False, path2, cell, cell.path))

        def find_external_connections_context(ctx, path, parent_path, parent_owns):
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
                    find_external_connections_cell(child, path2, parent_path2, owns)
                elif isinstance(child, Process):
                    find_external_connections_process(child, path2, parent_path2, owns)
                elif isinstance(child, Context):
                    find_external_connections_context(child, path2, parent_path2, owns)
                else:
                    raise TypeError((childname, child))

        if isinstance(parent, Cell):
            find_external_connections_cell(parent, None, None, None)
        elif isinstance(parent, Process):
            find_external_connections_process(parent, None, None, None)
        elif isinstance(parent, Context):
            find_external_connections_context(parent, None, None, None)
        elif parent is None:
            pass

        new_parent = self.macro.evaluate(self.args, self.kwargs, self)
        setattr(grandparent, parent_childname, new_parent) #destroys parent and connections
        self._parent = weakref.ref(new_parent)

        def resolve_path(target, path, index):
            if path is not None and len(path) > index:
                try:
                    new_target = getattr(target, path[index])
                except AttributeError:
                    warn = "WARNING: cannot reconstruct connections for '{0}', target no longer exists"
                    subpath = "." + ".".join(target.path + path[:index+1])
                    print(warn.format(subpath))
                    return None
                return resolve_path(new_target, path, index+1)
            return target

        for is_incoming, source, dest, ext_path in external_connections:
            print("CONNECTION: is_incoming {0}, source {1}, dest {2}".format(is_incoming, source, dest))
            err = "Connection {0}::(is_incoming {1}, source {2}, dest {3}) points to a destroyed external cell"
            if is_incoming:
                if source._destroyed:
                    print("ERROR:", err.format(new_parent.path, is_incoming, ext_path, dest) + " (source)")
                dest_target = resolve_path(new_parent, dest, 0)
                if dest_target is not None:
                    source.connect(dest_target)
            else:
                if dest._destroyed:
                    print("ERROR:", err.format(new_parent.path, is_incoming, source, ext_path) + " (dest)")
                    continue
                source_target = resolve_path(new_parent, source, 0)
                if source_target is not None:
                    source_target.connect(dest)

    def set_registrar_listeners(self, registrar_listeners):
        for registrar, manager, key in registrar_listeners:
            manager.add_registrar_listener(registrar, key, self, None)

    def __del__(self):
        if self._parent is None:
            return
        for k in self.cell_args:
            cell = self.cell_args[k]
            cell.remove_macro_object(self, k)
