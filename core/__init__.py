import weakref

class SeamlessBase:
    _destroyed = False
    _macro_object = None # macro object that CREATED this instance
    _context = None
    name = None

    def __init__(self):
        self._owned = []
        self._owner = None

    @property
    def path(self):
        if self._context is None:
            if self.name is None:
                return ()
            else:
                return (self._name,)
        else:
            return self._context.path + (self.name,)

    def _validate_path(self, required_path=None):
        if required_path is None:
            required_path = self.path
        else:
            assert self.path == required_path, (self.path, required_path)
        return required_path

    def _set_context(self, context, name, force_detach=False):
        from .context import Context
        assert isinstance(context, Context)
        if self._context is not None:
            assert self.name is not None
            if context is not self._context or force_detach:
                print("DETACH", self.name, self._context, name, context)
                childname = self.name
                assert self._context._children[childname] is self
                self._context._children.pop(childname)
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
        assert isinstance(obj, (Cell, Process, Context)), type(obj)
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
            obj._owner = weakref.ref(self)


    def _owns_all(self):
        owns = set(self._owned)
        for owned in self._owned:
            owns.update(owned._owns_all())
        return owns

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        ctx = self._context
        if ctx is not None:
            for childname, child in ctx._children.items():
                if child is self:
                    ctx._children.pop(childname)
                    break
        for obj in self._owned:
            obj.destroy()


    def __str__(self):
        return str(self.path)

    @property
    def macro(self):
        return self._macro_object
    def _set_macro_object(self, macro_object):
        self._macro_object = macro_object

    def __del__(self):
        try:
            self.destroy()
        except:
            pass
