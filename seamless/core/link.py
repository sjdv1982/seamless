def link(obj):
    return Link(obj)

from . import SeamlessBase

link_counter = 0
class Link(SeamlessBase):
    _mount = None
    def __init__(self, obj):
        from . import macro_register
        global link_counter
        assert isinstance(obj, SeamlessBase)
        self._linked = obj
        link_counter += 1
        self._counter = link_counter
        macro_register.add(self)

    def __hash__(self):
        return -self._counter

    @property
    def _seal(self):
        return self._linked._seal

    @_seal.setter
    def _seal(self, value):
        pass

    def get_linked(self):
        linked = self._linked
        if isinstance(linked, Link):
            linked = linked.get_linked()
        return linked

    def connect(self, target):
        manager = self._get_manager()
        manager.connect_link(self, target)
        return self

    def __getattr__(self, attr):
        from .layer import Path
        linked = self.get_linked()
        result = getattr(linked, attr)
        if isinstance(result, Path):
            return getattr(Path(self), attr)
        else:
            return result

    def __str__(self):
        ret = "Seamless link: %s to %s" % (self._format_path(), self._linked)
        return ret
