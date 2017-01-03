class SeamlessBase:
    _destroyed = False
    _macro_object = None # macro object that CREATED this instance
    _context = None

    def __init__(self):
        self._owned = []

    def _set_context(self, context, force_detach=False):
        from .context import Context
        assert isinstance(context, Context)
        if self._context is not None:
            if context is not self._context or force_detach:
                for childname, child in self._context._children.items():
                    if child is self:
                        self._context._children.pop(childname)
                        break
                else:
                    print("WARNING, orphaned child?")
        self._context = context
        return self

    @property
    def context(self):
        return self._context

    def own(self, obj):
        from .context import Context
        from .process import Managed
        assert isinstance(obj, (Managed, Context))
        if obj not in self._owned:
            self._owned.append(obj)

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
