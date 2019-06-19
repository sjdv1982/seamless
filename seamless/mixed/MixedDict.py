from numpy import ndarray, void
from collections.abc import MutableMapping
from . import MixedBase, is_np_struct
from .get_form import get_form_dict

class MixedDict(MixedBase, MutableMapping):
    def __getitem__(self, item):
        path = self._path + (item,)
        return self._monitor.get_path(path)
    def __setitem__(self, item, value):
        path = self._path + (item,)
        self._monitor.set_path(path, value)
    def __delitem__(self, item):
        path = self._path + (item,)
        self._monitor.del_path(path)
    def __iter__(self):
        data = self._monitor.get_data(self._path)
        if data is None:
            data = {}
        return iter(data)
    def __len__(self):
        data = self._monitor.get_data(self._path)
        if data is None:
            data = {}
        return len(data)
    def clear(self):
        data = self._monitor.get_data(self._path)
        for path in list(data.keys()):
            if isinstance(path, str):
                path = (path,)
            self._monitor.del_path(path)
    def update(self, other):
        if isinstance(other, MixedBase):
            other = other.value
        for k,v in other.items():
            path = self._path + (k,)
            self._monitor.set_path(path, v)


class MixedNumpyStruct(MixedBase, MutableMapping):
    def __getitem__(self, item):
        path = self._path + (item,)
        return self._monitor.get_path(path)
    def __setitem__(self, item, value):
        path = self._path + (item,)
        self._monitor.set_path(path, value)
    def __delitem__(self, item):
        raise TypeError("Cannot delete Numpy struct item '%s'" % item)
    def __iter__(self):
        data = self._monitor.get_data(self._path)
        return data.dtype.fields
    def __len__(self):
        data = self._monitor.get_data(self._path)
        return len(data.dtype.fields)

