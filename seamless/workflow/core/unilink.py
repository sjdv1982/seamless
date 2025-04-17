def unilink(obj):
    return UniLink(obj)


from . import SeamlessBase

link_counter = 0


class UniLink(SeamlessBase):
    _mount = None

    def __init__(self, obj):
        from .cell import Cell

        global link_counter
        assert isinstance(obj, Cell), obj  # only cells can be linked to!
        self._linked = obj
        link_counter += 1
        self._counter = link_counter

    def _set_context(self, ctx, name):
        from .unbound_context import UnboundContext

        super()._set_context(ctx, name)
        if isinstance(ctx, UnboundContext):
            manager = self._get_manager()
            manager._registered.add(self)

    def get_linked(self):
        linked = self._linked
        if isinstance(linked, UniLink):
            linked = linked.get_linked()
        return linked

    def connect(self, target):
        return self.get_linked().connect(target)

    def __getattr__(self, attr):
        linked = self.get_linked()
        result = getattr(linked, attr)
        return result

    def __str__(self):
        ret = "Seamless unilink: %s to %s" % (self._format_path(), self._linked)
        return ret
