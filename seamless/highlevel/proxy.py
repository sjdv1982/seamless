import weakref

class Proxy:
    def __init__(self, parent, path, mode, pull_source=None):
        self._parent = weakref.ref(parent)
        self._path = path
        self._mode = mode
        self._pull_source = pull_source

    def __rshift__(self, other):
        assert "w" in self._mode
        assert isinstance(other, Proxy)
        assert "r" in other._mode
        assert other._pull_source is not None
        other._pull_source(self)

    def __str__(self):
        return "<does not exist>"

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        raise NotImplementedError

    def __getattr__(self, attr):
        raise NotImplementedError
