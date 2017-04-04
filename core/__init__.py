import weakref


class SeamlessBase:
    _destroyed = False
    _macro_object = None  # macro object that CREATED this instance
    _context = None
    _last_context = None
    name = None

    def __init__(self):
        self._owned = []
        self._owner = None

    @property
    def path(self):
        if self._context is None:
            return ()
        else:
            return self._context.path + (self.name,)

    def _validate_path(self, required_path=None):
        if required_path is None:
            required_path = self.path
        else:
            assert self.path == required_path, (self.path, required_path)
        return required_path

    def _find_successor(self):
        path = list(self.path)
        node = self
        subpath = []

        while node._destroyed:
            if not path:
                break

            node = node._last_context
            if node is None:
                break

            subpath = [path.pop(-1)] + subpath

        if not node._destroyed:
            for subp in subpath:
                try:
                    node = getattr(node, subp)
                    assert not node._destroyed
                except:
                    break

            else:
                return node

    def _set_context(self, context, name, force_detach=False):
        from .context import Context
        assert isinstance(context, Context)
        self_context = self._context

        if self_context is not None:
            assert self.name is not None
            if context is not self_context or force_detach:
                child_name = self.name
                assert self_context._children[child_name] is self
                self_context._children.pop(child_name)
                if child_name in self_context._auto:
                    self_context._auto.remove(child_name)

        if context is not None:
            self._last_context = context

        self._context = context
        self.name = name
        return self

    @property
    def context(self):
        return self._context

    def own(self, obj):
        from .cell import Cell
        from .context import Context
        from .process import Process
        from .macro import get_macro_mode
        assert isinstance(obj, (Cell, Process, Context)), type(obj)
        assert obj is not self
        if self._owner is not None:
            owner = self._owner()
            if owner is not None:
                exc = "{0} cannot own, it is already owned by {1}"
                raise Exception(exc.format(self, owner))
            self._owner = None
        if obj not in self._owned:
            self._owned.append(obj)
            if obj._owner is not None:
                owner = obj._owner()
                if owner is not None:
                    if obj in owner._owned:
                        owner._owned.remove(obj)
            obj._owner = None
            macro_control = self._macro_control()
            if not get_macro_mode() and \
                            macro_control is not None and macro_control is not obj._macro_control():
                macro_cells = macro_control._macro_object.cell_args.values()
                macro_cells = sorted([str(c) for c in macro_cells])
                macro_cells = "\n  " + "\n  ".join(macro_cells)
                if macro_control is self:
                    print("""***********************************************************************************************************************
WARNING: {0} is now owned by {1}, which is under live macro control.
The macro is controlled by the following cells: {2}
When any of these cells change and the macro is re-executed, the owned object will be deleted and likely not re-created
***********************************************************************************************************************""" \
                          .format(obj, self, macro_cells))
                elif macro_control is not None:
                    print("""***********************************************************************************************************************
WARNING: {0} is now owned by {1}, which is a child of, or owned by, {2}, which is under live macro control.
The macro is controlled by the following cells: {3}
When any of these cells change and the macro is re-executed, the owned object will be deleted and likely not re-created
***********************************************************************************************************************""" \
                          .format(obj, self, macro_control, macro_cells))
            obj._owner = weakref.ref(self)

    def _owns_all(self):
        # TODO instead, can the leaf owns_all just include self in owns list?
        return set(self._owned) | {o._owns_all() for o in self._owned}

    def _macro_control(self, include_owner=False, primary=True, done=None):
        if self._macro_object is not None:
            return self

        if done is None:
            done = []

        if self in done:
            msg = "Ownership circle:\n    " + "\n    ".join([str(x) for x in done])
            raise Exception(msg)

        done.append(self)

        if self.context is not None:
            control = self.context._macro_control(include_owner, False, done)
            if control is not None:
                return control

        if include_owner and self._owner is not None:
            owner = self._owner()
            if owner is not None:
                control = owner._macro_control(True, False)
                if control is not None:
                    return control

        elif primary:
            return self._macro_control(True, True)
        else:
            return None

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True

        ctx = self._context
        if ctx is not None:
            for name, child in ctx._children.items():
                if child is self:
                    ctx._children.pop(name)
                    break

            ctx._manager.unstable_processes.discard(self)

        for obj in self._owned:
            obj.destroy()

    def __str__(self):
        text = "." + ".".join(self.path)
        if self._owner is not None:
            owner = self._owner()
            if owner is not None:
                text = "{}, owned by {}".format(text, owner)
        return text

    def __repr__(self):
        return self.__str__()

    @property
    def macro(self):
        return self._macro_object

    def _set_macro_object(self, macro_object):
        self._macro_object = macro_object

    def __del__(self):
        # print("__del__", type(self), self.path, self._destroyed)
        try:
            self.destroy()
        except:
            pass
