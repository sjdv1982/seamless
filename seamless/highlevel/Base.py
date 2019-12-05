import weakref

class Base:
    _parent = lambda self: None
    _path = None
    def __init__(self, parent, path):
        if parent is not None:
            self._parent = weakref.ref(parent)
        if isinstance(path, str):
            path = (path,)
        self._path = path

    @property
    def self(self):
        return self ### TODO: proper implementation
