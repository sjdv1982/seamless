from numpy import ndarray, void
from collections.abc import MutableMapping
from . import MixedBase
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
        return iter(data)
    def __len__(self):
        data = self._monitor.get_data(self._path)
        return len(data)

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

from .Monitor import Monitor

def mixed_dict(data, storage=None, form=None, *, MonitorClass=Monitor, **args):
    if not isinstance(data, MutableMapping) and not is_np_struct(data):
        raise TypeError(type(data))
    if isinstance(data, MixedDict):
        return MixedDict(data._monitor, data._path)
    else:
        if form is None:
            storage, form = get_form_dict(data)
        monitor = MonitorClass(data, storage, form, **args)
        return MixedDict(monitor, ())
