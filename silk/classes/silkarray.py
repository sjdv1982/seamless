import numpy as np
from collections import OrderedDict
import weakref
import copy

from ..registers import typenames
from . import SilkObject
from .silk import _prop_setter_any, _prop_setter_json

class _ArrayInsertContext:
    def __init__(self, arr, index):
        self.arr = arr
        self.index = index
    def __enter__(self):
        if issubclass(self.arr._element, SilkArray):
            ele = []
        else:
            ele = {}
        self.arr._data.insert(self.index, ele)
    def __exit__(self, type, value, traceback):
        if type is not None:
            self.arr._data.pop(self.index)
        else:
            self.arr._len += 1

class SilkArray(SilkObject):
    _element = None
    _dtype = None
    _elementary = None
    _arity = None
    __slots__ = (
        "_parent", "_storage_enum",
        "_data", "_children",
        "_len"
    )

    def __init__(self, *args, _mode="any", **kwargs):
        self._storage_enum = None
        if _mode == "parent":
            self._init(
                kwargs["parent"],
                kwargs["storage"],
                kwargs["data_store"],
            )
        else:
            self._init(None, "json", None)
            if _mode == "any":
                self.set(*args)
            elif _mode == "empty":
                pass
            elif _mode == "from_json":
                self.set(*args, prop_setter=_prop_setter_json)
            else:
                raise NotImplementedError

    def _init(self, parent, storage, data_store):
        self._len = 0
        if parent is not None:
            self._parent = weakref.ref(parent)
        else:
            self._parent = lambda: None
        self._storage = storage
        if storage == "json":
            if data_store is None:
                data_store = []
        else:
            assert data_store is not None
            assert data_store.dtype == self._dtype


        self._data = data_store
        self._children = []
        for n in range(len(self._data)):
            if self._storage == "json":
                if n > len(data_store):
                    if issubclass(self._element, SilkArray):
                        self._data.append([])
                    else:
                        self._data.append({})
            elif self._storage == "numpy":
                pass
            else:
                raise ValueError(self._storage)
            child = self._element(
              _mode="parent",
              storage=self._storage,
              parent=self,
              data_store=self._data[n]
            )
            self._children.append(child)

    def copy(self, storage="json"):
        """Returns a copy with the storage in the specified format"""
        if storage == "json":
            json = self.json()
            return cls.from_json(json, copy=False)
        elif storage == "numpy":
            numpydata = self.numpy()
            return cls.from_numpy(numpydata, copy=False)
        else:
            raise ValueError(storage)

    @classmethod
    def from_json(cls, data, copy=True):
        if not copy:
            raise NotImplementedError
        return cls(data, _mode="from_json")

    @classmethod
    def from_numpy(cls, data, copy=True):
        if not copy:
            raise NotImplementedError
        return cls(data, _mode="from_numpy")

    @classmethod
    def empty(cls):
        return cls(_mode="empty")

    def set(self, *args, prop_setter=_prop_setter_any):
        # TODO: make a nice composite exception that stores all exceptions
        try:
            self._construct(prop_setter, *args)
        except:
            if len(args) == 1 and len(kwargs) == 0:
                try:
                    a = args[0]
                    if isinstance(a, str):
                        self._parse(a)
                    elif isinstance(a, list) or isinstance(a, tuple):
                        self._construct(prop_setter, *a)
                    elif isinstance(a, SilkArray):
                        self._construct(prop_setter, *a._data)
                    else:
                        raise TypeError(a)
                except:
                    raise
            else:
                raise
        self.validate()

    def validate(self):
        pass

    def json(self):
        if not len(self._data):
            return None

        if self._storage == "json":
            return copy.deepcopy(self._data)

        if self._elementary:
            return [dd for dd in self._data]
        else:
            d = []
            for child in self._children:
                dd = child.json()
                d.append(dd)
        return d

    def make_numpy(self):
        if self._storage == "numpy":
            return self._data[:self._len]
        npname = self._storage_names.index("numpy")
        if not len(self._data):
            self._storage_enum = npname
            return
        shape = [len(self._data)]
        d = self._data
        for n in range(1, self._arity):
            d = [dd._data for dd in d]
            maxlen = max([len(dd) for dd in d])
            shape.append(maxlen)
            d = sum(d, [])

        old_data = self.json()
        data = np.zeros(dtype=self._dtype, shape=shape)
        self._init(self._parent(), "numpy", data)
        self._storage_enum = npname
        if self._elementary:
            self._data[:len(old_data)] = old_data
        else:
            for n in old_data:
                self._children[n].set(old_data[n])

    def _construct(self, prop_setter, *args):
        if self._storage == "numpy":
            if len(args) > len(data):
                msg = "index {0} is out of bounds for axis with size {1}"\
                      .format(len(args), len(data))
                raise IndexError(msg)
            if self._elementary:
                self._data[:len(args)] = args
            else:
                for anr, a in enumerate(args):
                    self._children[anr].set(args[n], prop_setter=prop_setter)
        else:
            if self._elementary:
                newdata = []
                for anr, a in enumerate(args):
                    v = self._element(a)
                    newdata.append(v)
                self._data[:] = newdata
            else:
                for n in range(self._len, len(args)):
                    if issubclass(self._element, SilkArray):
                        self._data.append([])
                    else:
                        self._data.append({})
                    child = self._element(
                      _mode="parent",
                      storage=self._storage,
                      parent=self,
                      data_store=self._data[n]
                    )
                    self._children.append(child)

                for n in range(len(args)):
                    child = self._children[n]
                    child.set(args[n], prop_setter=prop_setter)

                if len(args) < self._len:
                    self._children[:] = self._children[:len(args)]
                    self._data[:] = self._data[:len(args)]

        self._len = len(args)

    def _parse(self, s):
        raise NotImplementedError

    _storage_names = ("numpy", "json")

    @property
    def _storage(self):
        return self._storage_names[self._storage_enum]

    @_storage.setter
    def _storage(self, storage):
        assert storage in self._storage_names, storage
        self._storage_enum = self._storage_names.index(storage)

    def __getitem__(self, item):
        if not isinstance(item, int):
            msg = "{0} indices must be integers or slices, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       item.__class__.__name__))
        if self._elementary:
            return self._data[:self._len][item]
        else:
            return self._children[:self._len][item]

    def __setitem__(self, item, value):
        if not isinstance(item, int):
            msg = "{0} indices must be integers or slices, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       item.__class__.__name__))
        if self._elementary:
            self._data[:self._len][item].set(value)
        else:
            self._children[:self._len][item].set(value)

    def __delitem__(self, item):
        if not isinstance(item, int):
            msg = "{0} indices must be integers or slices, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       item.__class__.__name__))
        if self._elementary:
            self._data[:self._len][item]
            self._data.__delitem__(item)
        else:
            self._children[:self._len][item]
            self._children.__delitem__(item)

    def pop(self, item=-1):
        if not isinstance(item, int):
            msg = "{0} indices must be integers or slices, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       item.__class__.__name__))
        if self._elementary:
            ret = self._data[:self._len][item]
            self._data.__delitem__(item)
        else:
            ret = self._children[:self._len][item]
            self._children.__delitem__(item)
        return ret

    def __iter__(self, *args, **kwargs):
        if self._elementary:
            return self._data[:self._len].__iter__(*args, **kwargs)
        else:
            return self._children[:self._len].__iter__(*args, **kwargs)

    def __len__(self):
        return self._len

    def _print(self, spaces):
        ret = "{0} (\n".format(self.__class__.__name__)
        for n in range(self._len):
            if self._elementary:
                value = self._data[n]
                if self._storage == "numpy":
                    if value.dtype == '|S10':
                        substr = '"' + value.decode() + '"'
                    else:
                        substr = str(value)
                else:
                    substr = value._print(spaces+2)
            else:
                value = self._children[n]
                substr = value._print(spaces+2)
            ret += "{0}{1},\n".format(" " * (spaces+2), substr)
        ret += "{0})".format(" " * spaces)
        return ret

    def __str__(self):
        return self._print(0)

    def __repr__(self):
        return self._print(0)

    def clear(self):
        self.set([])

    def append(self, item):
        with _ArrayInsertContext(self, self._len):
            if self._storage == "numpy":
                if self._len >= len(self._data):
                    raise IndexError("Numpy array overflows allocated space")

            if self._elementary:
                self._data[self._len] = item
            else:
                child = self._element(
                  _mode="parent",
                  storage=self._storage,
                  parent=self,
                  data_store=self._data[self._len]
                )
                child.set(item)
                self._children.append(child)

    def insert(self, index, item):
        if self._storage == "numpy":
            if self._len >= len(self._data):
                raise IndexError("Numpy array overflows allocated space")

            if not self._elementary:
                backup_data = self._data[0][:]
                child = self._element(
                  _mode="parent",
                  storage=self._storage,
                  parent=self,
                  data_store=self._data[0],
                )
                child.set(item)
                child_data = self._data[0][:]
                self._data[index+1:self._len+1] = self._data[index:self._len]
                self._data[index][:] = child_data
                child._data = self._data[index]
                self._data[0][:] = backup_data
                self._children.insert(index, child)
                for n in range(index+1, self._len+1):
                    self._children[n]._data = self._data[n]
            else:
                self._data[self._len] = item  # dry run
                self._data[index+1:self._len+1] = self._data[index:self._len]
                self._data[index] = item  # should give no exception now


        else:
            with _ArrayInsertContext(self, index):
                if not self._elementary:
                    if issubclass(self._element, SilkArray):
                        data_store = []
                    else:
                        data_store = {}

                    child = self._element(
                      _mode="parent",
                      storage=self._storage,
                      parent=self,
                      data_store=data_store,
                    )
                    child.set(item)
                    self._children.insert(index, child)
