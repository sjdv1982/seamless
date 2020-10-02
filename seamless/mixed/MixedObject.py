from collections.abc import MutableMapping, MutableSequence
from . import MixedBase

class MixedObject(MixedBase, MutableMapping, MutableSequence):
    def _proxy(self):
        proxy = self._monitor.get_path(self._path)
        if isinstance(proxy, MixedObject):
            raise AttributeError(self._path)
        return proxy
    def _proxy2(self, item):
        proxy = self._monitor.get_path(self._path)
        if isinstance(proxy, MixedObject):
            if isinstance(item, int):
                self._monitor.set_path(self._path, [])
            elif isinstance(item, str):
                self._monitor.set_path(self._path, {})
            else:
                raise TypeError(item)
            proxy = self._proxy()
        return proxy
    def __getitem__(self, item):
        try:
            proxy = self._proxy2(item)
        except AttributeError:
            raise KeyError(item)
        return proxy.__getitem__(item)
    def __setitem__(self, item, value):
        proxy = self._proxy2(item)
        return proxy.__setitem__(item, value)
    def __delitem__(self, item):
        proxy = self._proxy()
        return proxy.__delitem__(item)
    def __iter__(self):
        proxy = self._proxy()
        return proxy.__iter__()
    def __len__(self):
        proxy = self._proxy()
        return proxy.__len__()
    def insert(self, item, value):
        proxy = self._proxy()
        return proxy.insert(item, value)
    def append(self, value):
        proxy = self._monitor.get_path(self._path)
        if isinstance(proxy, MixedObject):
            self._monitor.set_path(self._path, [])
            proxy = self._proxy()
        return proxy.append(value)
    def update(self, value):
        proxy = self._monitor.get_path(self._path)
        if isinstance(proxy, MixedObject):
            self._monitor.set_path(self._path, {})
            proxy = self._proxy()
        return proxy.update(value)
    def clear(self):
        proxy = self._monitor.get_path(self._path)
        if isinstance(proxy, MixedObject):
            self._monitor.set_path(self._path, {})
            proxy = self._proxy()
        return proxy.clear()
