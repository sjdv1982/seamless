from numpy import ndarray, void
from collections.abc import MutableSequence
from . import MixedBase
from .get_form import get_form_list

class MixedList(MixedBase, MutableSequence):
    def __getitem__(self, item):
        path = self._path + (item,)
        return self._monitor.get_path(path)
    def __setitem__(self, item, value):
        path = self._path + (item,)
        self._monitor.set_path(path, value)
    def insert(self, item, value):
        path = self._path + (item,)
        self._monitor.insert_path(path, value)
    def append(self, value):
        item = len(self)
        path = self._path + (item,)
        self._monitor.insert_path(path, value)
    def __delitem__(self, item):
        path = self._path + (item,)
        self._monitor.del_path(path)
    def __iter__(self):
        data = self._monitor.get_data(self._path)
        return iter(data)
    def __len__(self):
        data = self._monitor.get_data(self._path)
        return len(data)

class MixedNumpyArray(MixedBase, MutableSequence):
    def __getitem__(self, item):
        path = self._path + (item,)
        return self._monitor.get_path(path)
    def __setitem__(self, item, value):
        path = self._path + (item,)
        self._monitor.set_path(path, value)
    def insert(self, item, value):
        raise TypeError("Cannot insert Numpy array item '%d'" % item)
    def __delitem__(self, item):
        raise TypeError("Cannot delete Numpy array item '%d'" % item)
    def __iter__(self):
        data = self._monitor.get_data(self._path)
        return iter(data)
    def __len__(self):
        data = self._monitor.get_data(self._path)
        return len(data)

from .Monitor import Monitor

def mixed_list(data, storage=None, form=None, *,
  MonitorClass=Monitor, **args
):
    """Mostly for demonstration use (outside of contexts)"""
    if not isinstance(data, MutableMapping) and not is_np_struct(data):
        raise TypeError(type(data))
    if isinstance(data, MixedDict):
        return MixedDict(data._monitor, data._path)
    else:
        if form is None:
            storage, form = get_form_dict(data)
        if not isinstance(storage, (dict, list)):
            if "storage_hook" not in args:
                args["storage_hook"] = lambda v: v
        if not isinstance(form, (dict, list)):
            if "form_hook" not in args:
                args["form_hook"] = lambda v: v
        monitor = MonitorClass(data, storage, form, **args)
        return MixedList(monitor, ())
