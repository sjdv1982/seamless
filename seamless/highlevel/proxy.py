#TODO: add celltype and mimetype
import weakref

class Proxy:
    _getter = None
    def __init__(self, parent, path, mode, *, pull_source=None, getter=None, dirs=None):
        self._parent = weakref.ref(parent)
        self._path = path
        self._mode = mode
        self._pull_source = pull_source
        self._getter = getter
        self._dirs = dirs

    @property
    def _virtual_path(self):
        return self._parent()._path + self._path

    @property
    def authoritative(self):
        #TODO: determine if the proxy didn't get any inbound connections
        # If it did, you can't get another inbound connection, nor a link
        return True #for now, until implemented

    @property
    def links(self):
        #TODO: return the other partner of all Link objects with self in it
        return [] #stub

    def __rshift__(self, other):
        assert "w" in self._mode
        assert isinstance(other, Proxy)
        assert "r" in other._mode
        assert other._pull_source is not None
        other._pull_source(self)

    def __str__(self):
        path = self._parent()._path + self._path
        return "%s for %s" % (type(self).__name__, "." + ".".join(path))
            

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        elif attr == "example" and "example" in self._dirs:
            return getattr(self, "example").set(value)
        raise NotImplementedError

    def __getattr__(self, attr):
        if self._getter is None:
            raise AttributeError(attr)
        return self._getter(attr)

    def __dir__(self):
        result = list(object.__dir__(self))
        if self._dirs is not None:
            result += self._dirs
        return result

    def mount(self, *args, **kwargs):
        raise NotImplementedError

class CodeProxy(Proxy):
    """A subclass of Proxy that points to a code cell
    The main difference is that a CodeProxy behaves as a simple (non-structured)
    Cell when it comes to links and connections"""
    pass
