import weakref

class Base:
    _parent = lambda self: None
    _path = None
    def __init__(self, parent, path):
        from .Context import Context
        if parent is not None:
            assert isinstance(parent, Context)
            if parent._weak:
                self._parent = lambda: parent
            else:
                self._parent = weakref.ref(parent)
        if isinstance(path, str):
            path = (path,)
        self._path = path

    def _get_top_parent(self):
        from .Context import Context
        parent = self._parent()
        if isinstance(parent, Context):
            return parent
        else:
            return parent._get_parent()

    @property
    def self(self):
        return self ### TODO: proper implementation
