def link(obj):
    return Link(obj)

from . import SeamlessBase

link_counter = 0
class Link(SeamlessBase):
    _mount = None
    def __init__(self, obj):
        global link_counter
        assert isinstance(obj, SeamlessBase)
        self._linked = obj
        link_counter += 1
        self._counter = link_counter

    def __hash__(self):
        return -self._counter

    def get_linked(self):
        linked = self._linked
        if isinstance(linked, Link):
            linked = linked.get_linked()
        return linked

    def connect(self, target):
        return self.get_linked().connect(target)

    def __getattr__(self, attr):
        from .context import Path
        linked = self.get_linked()
        result = getattr(linked, attr)
        if isinstance(result, Path):
            return getattr(Path(self), attr)
        else:
            return result

    def __str__(self):
        ret = "Seamless link: %s to %s" % (self._format_path(), self._linked)
        return ret
