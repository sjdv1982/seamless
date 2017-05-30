import weakref
from .connection_finder import find_external_connections, \
  find_external_connections_cell, find_external_connections_worker, \
  find_internal_connections

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
        from .context import Context
        from .cell import CellLike
        from .worker import WorkerLike
        from .registrar import RegistrarObject
        assert (isinstance(parent, CellLike) and parent._like_cell) or \
         (isinstance(parent, WorkerLike) and parent._like_worker) or \
         (isinstance(parent, Context)) or \
         isinstance(parent, RegistrarObject), type(parent)
        #TODO: check that all cells and parent share a common root
        self._parent = weakref.ref(parent)
        for k in self.cell_args:
            cell = self.cell_args[k]
            cell.add_macro_object(self, k)

    def update_cell(self, cellname):
        from .. import debug
        from .macro import macro_mode_on
        from .context import Context
        from .cell import Cell
        from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase
        from .cache_signature import cache_signature
        from .registrar import RegistrarObject
        parent = self._parent()
        grandparent = parent.context
        assert isinstance(grandparent, Context), grandparent
        for parent_childname in grandparent._children:
            if grandparent._children[parent_childname] is parent:
                break
        else:
            exc = "Cannot identify parent-child relationship of macro context {0}"
            raise AttributeError(exc.format(parent))

        with_caching = self.macro.with_caching and isinstance(parent, Context)
        if with_caching:
            signature = cache_signature(parent)

        external_connections = []
        if isinstance(parent, Cell):
            find_external_connections_cell(external_connections, parent, None, None, None)
        elif isinstance(parent, Worker):
            find_external_connections_worker(external_connections, parent, None, None, None)
        elif isinstance(parent, Context):
            find_external_connections(external_connections, parent, None, None, None)
        elif isinstance(parent, RegistrarObject):
            pass
        elif parent is None:
            pass
        else:
            raise TypeError(type(parent))

        with macro_mode_on():
            new_parent = self.macro.evaluate(self.args, self.kwargs, self)
            new_signature = None
            if with_caching:
                old_internal_connections = []
                find_internal_connections(old_internal_connections, parent, None, None)
                try:
                    old_name = new_parent.name
                    new_parent.name = parent.name
                    new_signature = cache_signature(new_parent)
                finally:
                    new_parent.name = old_name
            if with_caching:
                setattr(grandparent, "@TEMP_CONTEXT", parent)
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

            transplanted = {}
            if with_caching: #transplant from old parent context into new parent context
                #TODO: this will only work as long as registrars/registries are global
                new_internal_connections = []
                find_internal_connections(new_internal_connections, new_parent, None, None)

                #build a set of to-be-transplanted children
                for childname, child in sorted(new_parent._children.items()):
                    assert not child._destroyed, childname
                    old_sig = signature.get(childname, None)
                    new_sig = new_signature[childname]
                    if old_sig == new_sig:
                        transplanted[childname] = getattr(parent, childname)

                manager = parent._manager

                #destroy internal connections that are no longer used
                for con in old_internal_connections:
                    n_intern = sum([c[0] in transplanted for c in con])
                    equiv = (con in new_internal_connections)
                    if n_intern == 0:
                        pass
                    elif n_intern == 1 or (n_intern == 2 and not equiv):
                        source = resolve_path(parent, con[0], 0)
                        dest = resolve_path(parent, con[1], 0)
                        source.disconnect(dest)
                    else: #n_intern == 2 and equiv
                        pass

                #transplant the children
                for childname in transplanted:
                    child = transplanted[childname]
                    c = manager.get_cell_id(child)
                    setattr(new_parent, childname, child)
                    assert manager.get_cell_id(getattr(new_parent, childname)) == c
                #destroy the remnants of the old context
                if with_caching:
                    delattr(grandparent, "@TEMP_CONTEXT")
                parent.destroy()

                #build new internal connections that didn't exist before
                for con in sorted(new_internal_connections):
                    n_intern = sum([c[0] in transplanted for c in con])
                    equiv = (con in old_internal_connections)
                    if n_intern == 0:
                        pass
                    elif n_intern == 1 or (n_intern == 2 and not equiv):
                        source = resolve_path(new_parent, con[0], 0)
                        dest = resolve_path(new_parent, con[1], 0)
                        source.connect(dest)
                    else: #n_intern == 2 and equiv
                        pass

            for mode, source, dest, ext_path in external_connections:
                if debug:
                    print("CONNECTION: mode '{0}', source {1}, dest {2}".format(mode, source, dest))
                err = "Connection {0}::(mode {1}, source {2}, dest {3}) points to a destroyed external cell"
                if mode in ("input", "rev_alias"):
                    if source._destroyed:
                        print("ERROR:", err.format(new_parent.path, mode, ext_path, dest) + " (source)")
                    if dest[0] in transplanted:
                        continue
                    dest_target = resolve_path(new_parent, dest, 0)
                    if dest_target is not None:
                        source.connect(dest_target)
                elif mode in ("output", "alias"):
                    if dest._destroyed:
                        print("ERROR:", err.format(new_parent.path, mode, source, ext_path) + " (dest)")
                        continue
                    if source[0] in transplanted:
                        continue
                    source_target = resolve_path(new_parent, source, 0)
                    if source_target is not None:
                        source_target.connect(dest)
                else:
                    #print("CONNECTION: mode '{0}', source {1}, dest {2}".format(mode, source, dest))
                    raise TypeError(mode)

    def set_registrar_listeners(self, registrar_listeners):
        for registrar, manager, key in registrar_listeners:
            manager.add_registrar_listener(registrar, key, self, None)

    def __del__(self):
        if self._parent is None:
            return
        for k in self.cell_args:
            cell = self.cell_args[k]
            cell.remove_macro_object(self, k)
