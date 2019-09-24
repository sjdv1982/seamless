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
        ###self._monitor.insert_path(path, value)
        self._monitor.set_path(path, value)
    def __delitem__(self, item):
        path = self._path + (item,)
        self._monitor.del_path(path)
    def __iter__(self):
        data = self._monitor.get_data(self._path)
        if data is None:
            data = []
        return iter(data)
    def __len__(self):
        data = self._monitor.get_data(self._path)
        if data is None:
            data = []
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

