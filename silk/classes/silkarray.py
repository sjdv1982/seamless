import numpy as np
from collections import OrderedDict
import weakref
import copy
import collections

from . import SilkObject, SilkStringLike
from .helpers import _prop_setter_any, _prop_setter_json, \
    _set_numpy_ele_prop, _set_numpy_ele_range, _get_numpy_ele_prop, \
    _filter_json


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
            dtype = np.dtype(self.arr._dtype, align=True)
            ele = np.zeros(shape=(1,), dtype=dtype)
            l = self.arr._len
            d = self.arr._data
            ind = self.index
            d[ind+1:l+1] = d[ind:l]
            try:
                d[ind] = ele[0]
            except ValueError:  # numpy bug
                for field in d.dtype.fields:
                    d[ind][field] = ele[0][field]
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
    __slots__ = [
        "_parent", "_storage_enum", "_storage_nonjson_children",
        "_data", "_children", "_len", "_is_none", "__weakref__"
    ]

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

    def _numpy_bind(self, data_store):
        self.storage = "numpy"
        assert data_store.dtype == np.dtype(self._dtype, align=True)
        assert len(data_store.shape) == self._arity
        self._data = data_store
        for childnr, child in enumerate(self._children):
            child._numpy_bind(data_store[childnr])
        parent = self._parent()
        if parent is not None:
            if parent.storage != "numpy":
                parent._add_nonjson_child(self)
            else:
                myname = parent._find_child(id(self))
                if not isinstance(parent, SilkArray) and \
                  parent._props[myname].get("var_array", False):
                    parent._data[myname] = self._data
                    parent._data["PTR_"+myname] = self._data.ctypes.data


    def _init(self, parent, storage, data_store):
        self._len = 0
        self._storage_nonjson_children.clear()
        if parent is not None:
            self._parent = weakref.ref(parent)
        else:
            self._parent = lambda: None
        if storage == "json":
            self.storage = "json"
            if data_store is None:
                data_store = []
        elif storage == "numpy":
            self.storage = "numpy"
            assert data_store is not None
            dtype = np.dtype(self._dtype, align=True)
            assert data_store.dtype == dtype
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
        self._is_none = False
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
        cls = type(self)
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
            data = _filter_json(data)
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
        if len(args) == 1:
            if args[0] is None:
                self._is_none = True
                self._len = 0
                if self.storage == "numpy":
                    self._data[:] = np.zeros_like(self._data)
                return
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
        self._is_none = False

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
        NOTE: for all numpy arrays,
          the entire storage buffer is returned,
          including (zeroed) elements if the data is not present!
          the length of each array is not stored, and must be obtained
           from the original SilkArray object
        """
        cls = type(self)
        if self.storage == "numpy":
            return self._data.copy()
        new_obj = self.copy("json")
        return new_obj.make_numpy()

    def make_json(self):
        if self.storage == "json":
            return self._data
        elif self.storage == "numpy":
            json = _filter_json(self.json(), self)
            parent = self._parent()
            if parent is not None and parent.storage == "numpy":
                parent.numpy_shatter()
            self._init(parent, "json", None)
            self.set(json, prop_setter=_prop_setter_json)
            if parent is not None:
                parent._remove_nonjson_child(self)
                myname = parent._find_child(id(self))
                parent._data[myname] = self._data
            return self._data
        elif self.storage == "mixed":
            for child in list(self._storage_nonjson_children):  # copy!
                child.make_json()
            # Above will automatically update storage status to "json"
            return self._data

    def _get_outer_shape(self):
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
        return shape

    def make_numpy(self):
        """Sets the internal storage to 'numpy'
        Returns the numpy array that is used as internal storage buffer
        NOTE: for all numpy arrays,
          the entire storage buffer is returned,
          including (zeroed) elements if the data is not present!
          the length/shape of each array is not stored, and must be obtained
           from the original SilkArray object
        """
        if self.storage == "numpy":
            return self._data
        dtype = np.dtype(self._dtype, align=True)
        shape = self._get_outer_shape()
        data = np.zeros(dtype=dtype, shape=shape)
        if self._elementary:
            self._set_numpy_ele_range(self, 0, len(self._data), self._data, self._arity, data)
        else:
            for childnr, child in enumerate(self._children):
                child.make_numpy()
                try:
                    data[childnr] = child._data
                except ValueError: #numpy bug
                    for field in child._data.dtype.names:
                        data[childnr][field] = child._data[field]
        self._numpy_bind(data)
        return data

    def realloc(self, *shape):
        assert self.storage == "numpy"
        parent = self._parent()
        if parent is not None:
            myname = parent._find_child(id(self))
            if parent.storage == "numpy":
                if not parent._props[myname].get("var_array", False):
                    raise Exception("Cannot reallocate numpy array that is\
part of a larger numpy buffer. Use numpy_shatter() on the parent to allow\
reallocation")
        if len(shape) != self._arity:
            msg = "Shape must have %d dimensions, not %d"
            raise ValueError(msg % (self._arity, len(shape)))
        min_shape = self._data.shape
        for n in range(self._arity):
            msg = "Dimension %d: shape must have at least length %d, not %d"
            if min_shape[n] > shape[n]:
                raise ValueError(msg % (n+1, min_shape[n], shape[n]))
        old_data = self._data
        self._data = np.zeros(dtype=self._dtype, shape=shape)
        slices = [slice(0,s) for s in min_shape]
        self._data[slices] = old_data
        if parent is not None:
            parent._data[myname] = self._data
            if parent._props[myname]["var_array"]:
                parent._data["PTR_"+myname] = self._data.ctypes.data


    def _find_child(self, child_id):
        for childname, ch in enumerate(self._children):
            if child_id == id(ch):
                return childname
        raise KeyError

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
                    parent._add_nonjson_child(self)

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
                    parent._remove_nonjson_child(self)

    def numpy_shatter(self):
        """
        Breaks up a unified numpy storage into one numpy storage per child
        """
        assert self.storage == "numpy"
        assert not self._elementary
        parent = self._parent()
        if parent is not None and parent.storage == "numpy":
            parent.numpy_shatter()
        data = []
        for child in self._children:
            d = child._data.copy()
            data.append(d)
            child._data = d
        self._data = data
        self._storage_nonjson_children = set([p for p in range(len(self._children))])
        self.storage = "mixed"

    def _get_lengths(self):
        if self._elementary:
            return "*" * self._len
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
                assert child.storage == "numpy"
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
                    _set_numpy_ele_range(self, 0, len(args), args, self._arity)
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

    def __setattr__(self, attr, value):
        if attr.startswith("_") or attr == "storage":
            object.__setattr__(self, attr, value)
        else:
            raise AttributeError

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

    def _set_prop(self, item, value, prop_setter=None):
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
            self._children[:self._len][item].set(value,prop_setter=prop_setter)

    def __setitem__(self, item, value):
        if isinstance(item, slice):
            start, stop, stride = item.indices(self._len)
            indices = list(range(start, stop, stride))
            if len(indices) != len(value):
                msg = "Cannot assign to a slice of length %d using \
a sequence of length %d"
                raise IndexError(msg % (len(indices), len(value)))
            for n in indices:
                self._set_prop(n, value[n])
            return
        elif isinstance(item, int):
            self._set_prop(item, value)
        else:
            msg = "{0} indices must be integers or slices, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       item.__class__.__name__))


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

    def pop(self, index=-1):
        if not isinstance(index, int):
            msg = "{0} indices must be integers, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       index.__class__.__name__))
        if index < 0:
            index += self._len
        if index < 0:
            raise IndexError
        if self.storage == "numpy":
            ret_data = self._data[:self._len][index].copy()
            ret = self._element(
                    _mode="ref",
                    storage="numpy",
                    data_store=ret_data
                )
            ret.set(self[index])
            self._data[index:self._len-1] = self._data[index+1:self._len]
            try:
                self._data[self._len-1] = np.zeros_like(self._data[self._len-1])
            except ValueError: # numpy bug
                for field in self._data.dtype.fields:
                    self._data[self._len-1][field] = np.zeros_like(self._data[self._len-1][field])
            if not self._elementary:
                self._children.pop(index)
        elif self._elementary:
            ret = self._data[:self._len][index]
            self._data.__delitem__(index)
        else:
            ret = self._children[:self._len][index]
            self._children.__delitem__(index)
            self._data.__delitem__(index)
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
        if not isinstance(index, int):
            msg = "{0} indices must be integers, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       index.__class__.__name__))
        if index < 0:
            index += self._len
        if index < 0:
            raise IndexError
        if self.storage == "numpy":
            if self._len >= len(self._data):
                raise IndexError("Numpy array overflows allocated space")
            if not self._elementary:
                backup_data = self._data[0].copy()
                child = self._element(
                  _mode="parent",
                  storage=self.storage,
                  parent=self,
                  data_store=self._data[0],
                )
                child.set(item)
                child_data = self._data[0].copy()
                self._data[index+1:self._len+1] = self._data[index:self._len]
                if index > 0:
                    self._data[index] = child_data
                    child._data = self._data[index]
                    self._data[0] = backup_data
                self._children.insert(index, child)
                for n in range(index+1, self._len+1):
                    self._children[n]._data = self._data[n]
            else:
                self._data[self._len] = item  # dry run
                self._data[index+1:self._len+1] = self._data[index:self._len]
                self._data[index] = item  # should give no exception now
            self._len += 1
        else:
            with _ArrayInsertContext(self, index):
                if self._elementary:
                    self._data[index] = item
                else:
                    child = self._element(
                      _mode="parent",
                      storage=self.storage,
                      parent=self,
                      data_store=self._data[index],
                    )
                    child.set(item)
                    self._children.insert(index, child)

    def __eq__(self, other):
        if self.storage == other.storage:
            return self._data == other._data
        else:
            return self.json() == other.json()
