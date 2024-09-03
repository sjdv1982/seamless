# TODO: add celltype and mimetype
import weakref


class Pull:
    def __init__(self, proxy):
        self._proxy = proxy


class Proxy:
    _getter = None

    def __init__(
        self,
        parent,
        path,
        mode,
        *,
        pull_source=None,
        getter=None,
        dirs=None,
        setter=None,
        deleter=None
    ):
        self._parent = weakref.ref(parent)
        self._path = path
        self._mode = mode
        self._pull_source = pull_source
        self._getter = getter
        if mode == "r":
            assert setter is None
        self._setter = setter
        self._deleter = deleter
        self._dirs = dirs

    @property
    def _virtual_path(self):
        ppath = self._parent()._path
        if ppath is None:
            return self._path
        return ppath + self._path

    def pull(self):
        if self._pull_source is None:
            raise AttributeError
        return Pull(self)

    def __str__(self):
        path = self._parent()._path + self._path
        return "%s for %s" % (type(self).__name__, "." + ".".join(path))

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        elif attr == "example" and "example" in self._dirs:
            return getattr(self, "example").set(value)
        elif self._mode == "r" or self._setter is None:
            raise AttributeError
        return self._setter(attr, value)

    def __getattr__(self, attr):
        if self._getter is None:
            raise AttributeError(attr)
        return self._getter(attr)

    def __delattr__(self, attr):
        if self._deleter is None:
            raise AttributeError
        return self._deleter(attr)

    def __dir__(self):
        result = list(object.__dir__(self))
        if self._dirs is not None:
            result += self._dirs
        return result


class CodeProxy(Proxy):
    """A subclass of Proxy that points to a code cell
    The main difference is that a CodeProxy behaves as a simple (non-structured)
    Cell when it comes to links and connections"""

    pass


class HeaderProxy(Proxy):
    """A subclass of Proxy that points to an auto-generated header cell of a compiled Transformer
    It behaves as a simple (non-structured) Cell that can be the source of connections
    """

    pass
