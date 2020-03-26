import weakref

from .Base import Base

class Module:
    def __init__(self, *, code=None, parent=None, path=None):
        raise NotImplementedError
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path)
        if code is not None:
            self.code = code