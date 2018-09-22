import weakref

class Base:
    _parent = None
    _path = None
    def __init__(self, parent, path):
        assert self._parent is None
        assert self._path is None
        self._parent = weakref.ref(parent)
        if isinstance(path, str):
            path = (path,)
        self._path = path
