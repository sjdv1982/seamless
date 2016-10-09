import numpy as np
from collections import OrderedDict
import weakref
import copy
import collections

from . import SilkObject, SilkStringLike
from .helpers import _prop_setter_any, _prop_setter_json, \
    _set_numpy_ele_prop, _set_numpy_ele_range, _get_numpy_ele_prop


class _ArrayConstructContext:
    def __init__(self, arr):
        self.arr = arr

    def __enter__(self):
        self.old_data = self.arr._data[:]
        self.old_children = self.arr._children[:]

    def __exit__(self, type, value, traceback):
        if type is not None:
            self.arr._data[:] = self.old_data
            self.arr._children[:] = self.old_children


class _ArrayInsertContext:
    def __init__(self, arr, index):
        self.arr = arr
        self.index = index

    def __enter__(self):
        if issubclass(self.arr._element, SilkArray):
            ele = []
        else:
            ele = {}
        if self.arr.storage == "numpy":
            ele = np.zeros(shape=(1,), dtype=self.arr._dtype)
            l = self.arr._len
            d = self.arr._data
            ind = self.index
            d[ind+1:l+1] = d[ind:l]
            d[ind] = ele
        else:
            self.arr._data.insert(self.index, ele)

    def __exit__(self, type, value, traceback):
        if type is not None:
            if self.arr.storage == "numpy":
                l = self.arr._len
                d = self.arr._data
                ind = self.index
                d[ind:l] = d[ind+1:l+1]
            else:
                self.arr._data.pop(self.index)
        else:
            self.arr._len += 1


class SilkArray(SilkObject):
    _element = None
    _dtype = None
    _elementary = None
    _arity = None
    _has_optional = None
    __slots__ = (
        "_parent", "_storage_enum", "_storage_nonjson_children"
        "_data", "_children", "_len"
    )

    def __init__(self, *args, _mode="any", **kwargs):
        self._storage_enum = None
        self._storage_nonjson_children = set()
        if _mode == "parent":
            self._init(
                kwargs["parent"],
                kwargs["storage"],
                kwargs["data_store"],
            )
        elif _mode == "ref":
            self._init(
                None,
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
                raise ValueError(_mode)

    def _init(self, parent, storage, data_store):
        self._len = 0
        self._storage_nonjson_children.clear()
        if parent is not None:
            self._parent = weakref.ref(parent)
        else:
            self._parent = lambda: None
        self.storage = storage
        if storage == "json":
            if data_store is None:
                data_store = []
        elif storage == "numpy":
            assert data_store is not None
            assert data_store.dtype == self._dtype
            self._data = data_store
            # data does NOT define the length of the array,
            #  only the maximum length!!
            # this has to be done later with a _set_lengths call
            self._len = 0
            self._children = []
            return
        else:
            raise ValueError(storage)

        self._data = data_store
        self._children = []
        for n in range(len(self._data)):
            if self.storage == "json":
                if n > len(data_store):
                    if issubclass(self._element, SilkArray):
                        self._data.append([])
                    else:
                        self._data.append({})
            else:
                raise ValueError(self.storage)
            if not self._elementary:
                child = self._element(
                  _mode="parent",
                  storage=self.storage,
                  parent=self,
                  data_store=self._data[n]
                )
                self._children.append(child)
        self._len = len(self._data)

    def copy(self, storage="json"):
        """Returns a copy with the storage in the specified format"""
        if storage == "json":
            json = self.json()
            return cls.from_json(json, copy=False)
        elif storage == "numpy":
            numpydata = self.numpy()
            return cls.from_numpy(numpydata, copy=False, copy_len=self)
        else:
            raise ValueError(storage)

    @classmethod
    def from_json(cls, data, copy=True):
        if not copy:
            return cls(_mode="ref", storage="json", data_store=data)
        else:
            return cls(data, _mode="from_json")

    @classmethod
    def from_numpy(cls, arr, copy=True, lengths=None, validate=True):
        """Constructs from a numpy array "arr"
        "lengths": The lengths of the array elements
          If specified, "lengths" must either be a SilkArray of type "cls",
            or a nested tuple returned by a SilkArray._get_lengths() call
          If not specified, it is assumed that "arr" is unpadded,
            i.e. that all elements have a valid value
        """
        if len(arr.shape) != self._arity:
            raise TypeError("arr must be %d-dimensional" % self._arity)
        if arr.dtype != self._dtype:
            raise TypeError("arr has the wrong dtype")

        if copy:
            arr = arr.copy()
        ret = cls(_mode="ref", storage="numpy", data_store=arr)
        if lengths is None:
            ret._set_lengths_from_data()
        else:
            ret._set_lengths(lengths)
        if validate:
            ret.validate()
        return ret


    @classmethod
    def empty(cls):
        return cls(_mode="empty")

    def set(self, *args, prop_setter=_prop_setter_any):
        # TODO: make a nice composite exception that stores all exceptions
        try:
            if self.storage == "numpy" and \
              len(args) == 1 and len(kwargs) == 0 and \
              isinstance(args[0], np.ndarray):
                self._construct_from_numpy(args[0])
            else:
                raise TypeError("Not a numpy array")
        except:
            try:
                if len(args) == 1:
                    a = args[0]
                    if isinstance(a, str):
                        self._parse(a)
                    elif isinstance(a, SilkArray):
                        self._construct(prop_setter, *a._data)
                    elif isinstance(a, collections.Iterable) or isinstance(a, np.void):
                        self._construct(prop_setter, *a)
                    else:
                        raise TypeError(a)
                else:
                    raise TypeError(a)
            except:
                try:
                    self._construct(prop_setter, *args)
                except:
                    raise
        self.validate()

    def validate(self):
        pass

    def json(self):
        if not len(self._data):
            return None

        if self.storage == "json":
            return copy.deepcopy(self._data)

        if self._elementary:
            return [dd for dd in self._data]
        else:
            d = []
            for child in self._children:
                dd = child.json()
                d.append(dd)
        return d

    def numpy(self):
        """Returns a numpy representation of the Silk array
        NOTE: for Silk arrays, the entire storage buffer is returned,
         including (zeroed) elements beyond the current length!
        """
        if self.storage == "numpy":
            return self._data.copy()
        d = self._data
        shape = []
        for n in range(1, self._arity):
            d = [dd for dd in d]
            maxlen = max([len(dd) for dd in d])
            shape.append(maxlen)
            d = sum(d, [])
        ret = self._data
        for maxlen in shape:
            ret = ret[slice(0, maxlen)]
        return ret

    def make_json(self):
        if self.storage == "json":
            return self._data
        elif self.storage == "numpy":
            json = self.json()
            parent = self._parent()
            self._init(parent, "json", json)
            if parent is not None:
                parent._remove_nonjson_child(self)
            return json
        elif self.storage == "mixed":
            for child in list(self._storage_nonjson_children):  # copy!
                child.make_json()
            # Above will automatically update storage status to "json"
            return self._data

    def make_numpy(self):
        """Sets the internal storage to 'numpy'
        Returns the numpy array that is used as internal storage buffer
        NOTE: for Silk arrays, the internal storage buffer may include
         (zeroed) elements beyond the current length!
        """
        if self.storage == "numpy":
            return self._data

        old_data = self.json()
        assert len(self._children) == len(self._data)
        assert len(old_data) == len(self._data)
        backup_data = self._data
        backup_children = self._children
        backup_storage_enum = self._storage_enum
        backup_storage_nonjson_children = self._storage_nonjson_children
        ok = False
        lengths = self._get_lengths()
        shape = [len(self)]
        d = self
        for n in range(1, self._arity):
            maxlen = max([len(dd) for dd in d])
            shape.append(maxlen)
            d2 = []
            for dd in d:
                for ddd in dd:
                    d2.append(ddd)
            d = d2
        try:
            data = np.zeros(dtype=self._dtype, shape=shape)
            assert len(data) == len(old_data), old_data
            self._init(self._parent(), "numpy", data)
            self._set_lengths(lengths)
            self.storage = "numpy"
            if self._elementary:
                if self._data.dtype.kind in ('S', 'U'):
                    _set_numpy_ele_range(self, 0, len(old_data), old_data)
                else:
                    self._data[:len(old_data)] = old_data
            else:
                assert len(old_data) == len(self._children), \
                  (len(old_data), len(self._children))
                for n in range(len(old_data)):
                    self._children[n].set(old_data[n])
            parent = self._parent()
            if parent is not None:
                parent._add_nonjson_child(self)
            ok = True
        finally:
            if not ok:
                self._data = backup_data
                self._children = backup_children
                self._storage_enum = backup_storage_enum
                self._storage_nonjson_children = \
                    backup_storage_nonjson_children
        return data

    def _add_nonjson_child(self, child):
        assert self.storage != "numpy"
        njc = self._storage_nonjson_children
        child_id = id(child)
        if child_id not in njc:
            njc.add(child_id)
            if self.storage == "json":
                self.storage = "mixed"
                parent = self._parent()
                if parent is not None:
                    parent()._add_nonjson_child(self)

    def _remove_nonjson_child(self, child):
        assert self.storage != "numpy"
        njc = self._storage_nonjson_children
        child_id = id(child)
        if child_id in njc:
            assert self.storage == "mixed", self.storage
            njc.remove(child_id)
            if len(njc) == 0:
                self.storage = "json"
                parent = self._parent()
                if parent is not None:
                    parent()._remove_nonjson_child(self)

    def _get_lengths(self):
        if self._elementary:
            return self._len
        else:
            ret = []
            for child in self._children:
                child_lengths = child._get_lengths()
                ret.append(child_lengths)
            return ret

    def _set_lengths_from_data(self):
        assert self.storage == "numpy"
        if len(self._children) > 0:
            raise ValueError("_children already defined")
        self._len = len(self._data)
        if not self._elementary:
            for n in range(self._len):
                child = self._element(
                  _mode="parent",
                  storage="numpy",
                  parent=self,
                  data_store=self._data[n]
                )
                child._set_lengths_from_data()
                self._children.append(child)

    def _set_lengths(self, lengths):
        assert self.storage == "numpy"
        if len(self._children) > 0:
            raise ValueError("_children already defined")
        if self._elementary:
            if not isinstance(lengths, int):
                msg = "'%s' requires int for length, found '%s'"
                raise TypeError(msg % (type(self), type(length)))
            assert lengths <= len(self._data)
            self._data[lengths:] = np.zeros_like(self._data[lengths:])
            self._len = lengths
        else:
            if not isinstance(lengths, collections.Iterable):
                msg = "'%s' requires list for length, found '%s'"
                raise TypeError(msg % (type(self), type(length)))
            assert len(lengths) <= len(self._data)
            l = len(lengths)
            self._len = l
            self._data[l:] = np.zeros_like(self._data[l:])
            for n in range(self._len):
                child_lengths = lengths[n]
                child = self._element(
                  _mode="parent",
                  storage="numpy",
                  parent=self,
                  data_store=self._data[n]
                )
                if child_lengths is not None:
                    child._set_lengths(child_lengths)
                self._children.append(child)

    def _construct(self, prop_setter, *args):
        old_data = self._data
        old_children = self._children
        with _ArrayConstructContext(self):
            if self.storage == "numpy":
                if len(args) > len(self._data):
                    msg = "index {0} is out of bounds for axis with size {1}"\
                          .format(len(args), len(data))
                    raise IndexError(msg)
                if self._elementary:
                    _set_numpy_ele_range(self, 0, len(args), args)
                else:
                    for anr, a in enumerate(args):
                        self._children[anr].set(args[anr],
                                                prop_setter=prop_setter)
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
                          storage=self.storage,
                          parent=self,
                          data_store=self._data[n]
                        )
                        self._children.append(child)

                    for n in range(len(args)):
                        child = self._children[n]
                        child.set(args[n], prop_setter=prop_setter)

                    if len(args) < self._len:
                        self._children[:] = self._children[:len(args)]
                        if self.storage == "numpy":
                            self._data[len(args):] = \
                              np.zeros_like(self._data[len(args):])
                        else:
                            self._data[:] = self._data[:len(args)]

        self._len = len(args)

    def _construct_from_numpy(self, arr):
        d = self._data
        if len(arr.shape) != len(d.shape) or arr.dtype != d.dtype:
            err = TypeError((len(arr.shape), len(d.shape), arr.dtype, d.dtype))
            raise err
        c = self._children
        ok = False
        try:
            self._data = arr.copy()
            self._children = []
            for n in range(len(arr)):
                child = self._element(
                  _mode="parent",
                  storage="numpy",
                  parent=self,
                  data_store=self._data[n]
                )
                self._children.append(child)
            self._len = len(arr)
            ok = True
        finally:
            if not ok:
                self._data = d
                self._children = c

    def _parse(self, s):
        raise NotImplementedError  # can be user-defined

    _storage_names = ("numpy", "json", "mixed")

    @property
    def storage(self):
        return self._storage_names[self._storage_enum]

    @storage.setter
    def storage(self, storage):
        assert storage in self._storage_names, storage
        self._storage_enum = self._storage_names.index(storage)

    def __getitem__(self, item):
        if not isinstance(item, int):
            msg = "{0} indices must be integers or slices, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       item.__class__.__name__))
        if self._elementary:
            if self.storage == "numpy":
                return _get_numpy_ele_prop(self, item, self._len)
            else:
                return self._data[:self._len][item]
        else:
            return self._children[:self._len][item]

    def __setitem__(self, item, value):
        if isinstance(item, slice):
            start, stop, stride = item.indices(self._len)
            indices = list(range(start, stop, stride))
            if len(indices) != len(value):
                msg = "Cannot assign to a slice of length %d using \
a sequence of length %d"
                raise IndexError(msg % (len(indices), len(value)))
            for n in indices:
                self.__setitem__(n, value[n])
            return
        elif not isinstance(item, int):
            msg = "{0} indices must be integers or slices, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       item.__class__.__name__))
        if self._elementary:
            if self.storage == "numpy":
                _set_numpy_ele_prop(self, item, value)
            else:
                if item < 0:
                    item = self._len - item
                elif item >= self._len:
                    raise IndexError(item)
                self._data[item] = self._element(value)
        else:
            self._children[:self._len][item].set(value)

    def __delitem__(self, item):
        if isinstance(item, slice):
            start, stop, stride = item.indices(self._len)
            indices = list(range(start, stop, stride))
            for n in indices:
                self.__delitem__(n)
            return
        if not isinstance(item, int):
            msg = "{0} indices must be integers or slices, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       item.__class__.__name__))
        if self.storage == "numpy":
            self._data[item:self._len-1] = self._data[item+1:self._len]
            self._data[self._len-1] = np.zeros_like(self._data[self._len-1])
            if not self._elementary:
                self._children.pop(-1)
        elif self._elementary:
            self._data[:self._len][item]
            self._data.__delitem__(item)
        else:
            self._children[:self._len][item]
            self._children.__delitem__(item)
            self._data.__delitem__(item)
            self._len -= 1

    def pop(self, item=-1):
        if not isinstance(item, int):
            msg = "{0} indices must be integers or slices, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       item.__class__.__name__))
        if self.storage == "numpy":
            ret_data = self._data[:self._len][item].copy()
            ret = self._element(
                    _mode="ref",
                    storage="numpy",
                    data_store=ret_data
                )
            self._data[item:self._len-1] = self._data[item+1:self._len]
            self._data[self._len-1] = np.zeros_like(self._data[self._len-1])
            if not self._elementary:
                self._children.pop(-1)
        elif self._elementary:
            ret = self._data[:self._len][item]
            self._data.__delitem__(item)
        else:
            ret = self._children[:self._len][item]
            self._children.__delitem__(item)
            self._data.__delitem__(item)
        self._len -= 1
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
                if self.storage == "numpy":
                    if value.dtype.kind == 'S':
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
        if self.storage == "numpy":
            if self._len >= len(self._data):
                raise IndexError("Numpy array overflows allocated space")
        with _ArrayInsertContext(self, self._len):
            if self._elementary:
                self._data[self._len] = item
            else:
                child = self._element(
                  _mode="parent",
                  storage=self.storage,
                  parent=self,
                  data_store=self._data[self._len]
                )
                child.set(item)
                self._children.append(child)

    def insert(self, index, item):
        if self._len >= len(self._data):
            raise IndexError("Numpy array overflows allocated space")
        if self.storage == "numpy":
            if not self._elementary:
                backup_data = self._data[0][:]
                child = self._element(
                  _mode="parent",
                  storage=self.storage,
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
                      storage=self.storage,
                      parent=self,
                      data_store=data_store,
                    )
                    child.set(item)
                    self._children.insert(index, child)

    def __eq__(self, other):
        if self.storage == other.storage:
            return self._data == other._data
        else:
            return self.json() == other.json()
