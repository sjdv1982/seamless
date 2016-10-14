import numpy as np
from collections import OrderedDict
import weakref
import copy
import collections
from .helpers import _get_lenarray_full, _get_lenarray_empty, _get_lenarray_size, _lenarray_copypad

from . import SilkObject, SilkStringLike
from .helpers import _prop_setter_any, _prop_setter_json, \
    _set_numpy_ele_prop, _set_numpy_ele_range, _get_numpy_ele_prop, \
    _filter_json, datacopy


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
        "_data", "_children", "_Len", "_is_none", "__weakref__"
    ]

    def __init__(self, *args, _mode="any", **kwargs):
        self._storage_enum = None
        self._storage_nonjson_children = set()
        if _mode == "parent":
            self._init(
                kwargs["parent"],
                kwargs["storage"],
                kwargs["data_store"],
                kwargs["len_data_store"],
                rebind=False
            )
        elif _mode == "ref":
            self._init(
                None,
                kwargs["storage"],
                kwargs["data_store"],
                kwargs["len_data_store"],
                rebind=False
            )
            for child in self._children:
                child._fix_numpy_ref()
        else:
            self._init(None, "json", None, None, rebind=False)
            if _mode == "any":
                self.set(*args)

            elif _mode == "empty":
                pass

            elif _mode == "from_json":
                self.set(*args, prop_setter=_prop_setter_json)

            else:
                raise ValueError(_mode)

    @property
    def _len(self):
        return int(self._Len[0])

    @_len.setter
    def _len(self, value):
        self._Len[0] = value

    def _fix_numpy_ref(self):
        for child in self._children:
            child._fix_numpy_ref()

    def _init(self, parent, storage, data_store, len_data_store, rebind):
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
            assert len_data_store is not None
            assert len(len_data_store), len_data_store
            dtype = np.dtype(self._dtype, align=True)
            assert data_store.dtype == dtype
            self._data = data_store
            self._Len = len_data_store
            if not rebind:
                self._construct_numpy_children()
            else:
                for childnr, child in enumerate(self._children):
                    child._data = self._data[childnr]
                    if self._arity > 1:
                        child._Len = self._get_child_lengths(childnr)
            return
        else:
            raise ValueError(storage)

        assert self.storage == "json"
        assert not rebind
        self._data = data_store
        self._children = []
        self._Len = [0]
        self._storage_nonjson_children.clear()
        self._is_none = False
        for n in range(len(self._data)):
            if n > len(data_store):
                if issubclass(self._element, SilkArray):
                    self._data.append([])
                else:
                    self._data.append({})
            if not self._elementary:
                child = self._element(
                  _mode="parent",
                  storage=self.storage,
                  parent=self,
                  data_store=self._data[n],
                  len_data_store=None,
                )
                self._children.append(child)
        self._len = len(self._data)

    def copy(self, storage="json"):
        """Returns a copy with the storage in the specified format"""
        cls = type(self)
        if storage == "json":
            json = self.json()
            return cls.from_json(json)
        elif storage == "numpy":
            numpydata, lengths = self.numpy()
            return cls.from_numpy(numpydata, lengths, copy=False)
        else:
            raise ValueError(storage)

    @classmethod
    def from_json(cls, data):
        data = _filter_json(data)
        return cls(data, _mode="from_json")

    @classmethod
    def _check_numpy_args(cls, arr, lengths, length_can_be_none, self_data):
        if self_data is not None:
            d = self_data
            if len(arr.shape) != len(d.shape) or arr.dtype != d.dtype:
                err = TypeError((len(arr.shape), len(d.shape), arr.dtype, d.dtype))
                raise err

        if len(arr.shape) != cls._arity:
            raise TypeError("Array must be %d-dimensional" % cls._arity)

        if arr.dtype != np.dtype(cls._dtype,align=True):
            raise TypeError("Array has the wrong dtype")

        if lengths is None and length_can_be_none:
            return

        assert lengths.dtype == np.uint16
        lenarray_shape = (_get_lenarray_size(arr.shape),)
        if lengths.shape != lenarray_shape:
            err = TypeError((lengths.shape, lenarray_shape, arr.shape))
            raise err

    @classmethod
    def from_numpy(cls, arr, lengths=None, *, copy=True, validate=True):
        """Constructs from a numpy array "arr"
        "lengths": The lengths of the array elements
          If not specified, it is assumed that "arr" is unpadded,
            i.e. that all elements have a valid value
        """
        if isinstance(arr, tuple) and len(arr) == 2 and \
          isinstance(arr[0], np.ndarray) and isinstance(arr[1], np.ndarray):
            return cls.from_numpy(arr[0], arr[1],
                copy=copy, validate=validate
            )
        cls._check_numpy_args(arr, lengths, length_can_be_none=True, self_data=None)

        if copy:
            arr = datacopy(arr)
        if lengths is None:
            lengths = _get_lenarray_full(arr.shape)
        ret = cls(_mode="ref", storage="numpy", data_store=arr,len_data_store=lengths)
        if validate:
            ret.validate()
        return ret


    @classmethod
    def empty(cls):
        return cls(_mode="empty")

    def set(self, *args, prop_setter=_prop_setter_any, **kwargs):
        if len(args) == 1:
            if args[0] is None:
                self._is_none = True
                self._len = 0
                self._clear_data()
                return

        # TODO: make a nice composite exception that stores all exceptions
        try:
            if self.storage == "numpy" and \
              len(args) == 1 and len(kwargs) == 0 and \
              isinstance(args[0], np.ndarray):
                self._construct_from_numpy(args[0], lengths=None)
            else:
                raise TypeError("Not a numpy array")

        except:
            try:
                keep_trying = True
                ok = False
                if len(args) == 1:
                    a = args[0]
                    if isinstance(a, str):
                        self._parse(a)
                    elif isinstance(a, SilkArray):
                        if a.storage == "numpy":
                            if isinstance(a, type(self)):
                                keep_trying = False
                                self._construct_from_numpy(a._data, a._Len)
                            else:
                                self._construct(prop_setter, a.json(), prop_setter=_prop_setter_json)
                        else:
                            self._construct(prop_setter, *a)
                    elif isinstance(a, collections.Iterable) or isinstance(a, np.void):
                        self._construct(prop_setter, *a)
                    else:
                        raise TypeError(a)
                else:
                    raise TypeError(args)
                ok = True

            except:
                if not ok:
                    if not keep_trying:
                        raise
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
            return _filter_json(self._data)

        if self._elementary:
            return [d for d in self._data]

        else:
            data_list = []
            for child in self._children:
                child_data = child.json()
                data_list.append(child_data)

        return data_list

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
            return datacopy(self._data), self._Len.copy()

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

            self._init(parent, "json", None, None, rebind=False)
            self.set(json, prop_setter=_prop_setter_json)

            if parent is not None:
                parent._remove_nonjson_child(self)
                myname = parent._find_child(id(self))
                parent._data[myname] = self._data

            return self._data

        elif self.storage == "mixed":
            for child_id in list(self._storage_nonjson_children):  # copy!
                for child in self._children:
                    if id(child) == child_id:
                        child.make_json()
                        break
                else:
                    raise Exception("Cannot find child that was marked as 'non-JSON'")

            # Above will automatically update storage status to "json"
            assert self.storage == "json"
            return self._data

    def _get_outer_shape(self):
        shape = [len(self)]
        d = self
        for n in range(1, self._arity):
            max_len = max([len(dd) for dd in d])
            shape.append(max_len)
            d2 = []

            for dd in d:
                d2.extend(dd)

            d = d2
        return shape

    def _get_child_lengths(self, child):
        if self.storage != "numpy":
            return None

        if self._arity == 1:
            return None

        child_size = _get_lenarray_size(self._data.shape[1:])
        start = 1 + child_size * child
        assert start+child_size <= len(self._Len)
        return self._Len[start:start+child_size]

    def _del_child_lengths(self, child):
        if self.storage != "numpy":
            return

        if self._arity == 1:
            return

        size = _get_lenarray_size(self._data.shape[1:])
        offset = 1 + size * child
        lsize = len(self._Len)
        self._Len[offset:lsize-size] = self._Len[offset+size:lsize]
        self._Len[lsize-size:] = 0

        for n in range(child+1, len(self._children)):
            c_offset = 1 + size * n
            c = self._children[n]
            c._Len = self._Len[c_offset:c_offset+size]

    def _insert_child_lengths(self, child, child_lengths):
        if self.storage != "numpy":
            assert child_lengths is None
            return

        if self._arity == 1:
            assert child_lengths is None
            return

        assert child_lengths is not None
        size = _get_lenarray_size(self._data.shape[1:])
        offset = 1 + size * child
        lsize = len(self._Len)
        self._Len[offset+size:lsize] = self._Len[offset:lsize-size]
        self._Len[offset:offset+size] = child_lengths
        for n in range(child, len(self._children)):
            c_offset = 1 + size * (n+1)
            c = self._children[n]
            c._Len = self._Len[c_offset:c_offset+size]

    def _restore_array_coupling(self):
        """
        Array members have their length vector stored in the parent data
        In addition, var_arrays have a pointer to their data stored
        If the parent data gets reallocated or copied, then
         this information gets decoupled, so it must be restored
        """
        for child in self._children:
            child._restore_array_coupling()

        parent = self._parent()
        if parent is None:
            return

        if parent.storage != "numpy":
            return

        myname = parent._find_child(id(self))
        if not isinstance(parent, SilkArray) and parent._props[myname].get("var_array", False):
            if not hasattr(parent, "_data"):
                return

            parent._data[myname] = self._data
            parent._data["PTR_"+myname] = self._data.ctypes.data
            parent._data["LEN_"+myname] = self._Len.copy()

            self._Len = parent._data["LEN_"+myname]
            if self._arity > 1:
                parent._data["PTR_LEN_"+myname] = self._Len.ctypes.data

    def make_numpy(self,_toplevel=True):
        """Sets the internal storage to 'numpy'
        Returns the numpy array that is used as internal storage buffer,
         and the length array that contains all lengths
        """
        if self.storage == "numpy":
            return self._data, self._Len

        dtype = np.dtype(self._dtype, align=True)
        shape = self._get_outer_shape()
        data = np.zeros(dtype=dtype, shape=shape)
        lengths = _get_lenarray_empty(shape)
        lengths[0] = len(self)

        if self._elementary:
            self._set_numpy_ele_range(self, 0, len(self._data), self._data, self._arity, data)

        else:
            for childnr, child in enumerate(self._children):
                child.make_numpy(_toplevel=False)
                if self._arity > 1:
                    slices = [slice(0,v) for v in child._data.shape]
                    data[childnr][slices] = child._data
                else:
                    try:
                        data[childnr] = child._data
                    except ValueError: #numpy bug
                        for field in child._data.dtype.names:
                            data[childnr][field] = child._data[field]
                if self._arity > 1:
                    child_size = _get_lenarray_size(shape[1:])
                    start = 1 + child_size * childnr
                    arr1 = lengths[start:start+child_size]
                    shape1 = data.shape[1:]
                    arr2 = child._Len
                    shape2 = child._data.shape
                    _lenarray_copypad(arr1, shape1, arr2, shape2)

        self._init(self._parent(), "numpy", data, lengths, rebind=True)
        parent = self._parent()
        if parent is not None:
            if parent.storage != "numpy":
                parent._add_nonjson_child(self)
        if _toplevel:
            self._restore_array_coupling()

        return data, lengths

    def realloc(self, *shape):
        assert self.storage == "numpy"
        if len(shape) == 1 and isinstance(shape[0], tuple):
            shape = shape[0]
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
        old_len = self._Len
        self._data = np.zeros(dtype=self._dtype, shape=shape)
        slices = [slice(0,s) for s in min_shape]
        self._data[slices] = old_data
        self._Len = _get_lenarray_empty(shape)
        _lenarray_copypad(self._Len, shape, old_len, old_data.shape)
        self._init(parent, "numpy", self._data, self._Len, rebind=True)
        self._restore_array_coupling()

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
            d = datacopy(child._data)
            data.append(d)
            child._data = d
        self._data = data
        self._storage_nonjson_children = set([p for p in range(len(self._children))])
        self.storage = "mixed"

    def _construct(self, prop_setter, *args):
        old_data = self._data
        old_children = self._children
        with _ArrayConstructContext(self):
            if self.storage == "numpy":
                if len(args) > len(self._data):
                    msg = "index {0} is out of bounds for axis with size {1}".format(len(args), len(self._data))
                    raise IndexError(msg)
                if self._elementary:
                    _set_numpy_ele_range(self, 0, len(args), args, self._arity)
                else:
                    for anr, a in enumerate(args):
                        if anr == len(self._children):
                            child = self._element(
                              _mode="parent",
                              parent=self,
                              storage="numpy",
                              data_store=self._data[anr],
                              len_data_store=self._get_child_lengths(anr),
                            )
                            self._children.append(child)
                        else:
                            child = self._children[anr]
                        child.set(args[anr],prop_setter=prop_setter)
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
                          data_store=self._data[n],
                          len_data_store=self._get_child_lengths(n)
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

    def _construct_numpy_children(self):
        assert self.storage == "numpy"
        assert len(self._Len)
        self._children = []
        if self._elementary:
            return
        for n in range(self._len):
            child = self._element(
              _mode="parent",
              storage="numpy",
              parent=self,
              data_store=self._data[n],
              len_data_store=self._get_child_lengths(n)
            )
            self._children.append(child)
        self._fix_numpy_ref()

    def _construct_from_numpy(self, arr, lengths):
        if self.storage != "numpy":
            self._init(self._parent(), "numpy", arr, lengths, rebind=False)
            self._fix_numpy_ref()
            self.make_json()
            return

        d = self._data
        l = self._Len
        c = self._children
        self._check_numpy_args(arr, lengths, self_data=self._data, length_can_be_none=False)
        if lengths is None:
            lengths = _get_lenarray_full(arr.shape)

        ok = False
        try:
            self._data = datacopy(arr)
            self._Len = lengths.copy()
            self._children = []
            self._construct_numpy_children()
            ok = True
        finally:
            if not ok:
                self._data = d
                self._Len = l
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
            raise AttributeError(attr)

    def __getitem__(self, item):
        if isinstance(item, slice):
            return type(self)([self[v] for v in range(*item.indices(len(self)))])
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

    def _set_prop(self, item, value, prop_setter=_prop_setter_any):
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
            for n in reversed(indices):
                self.pop(n)
            return
        if not isinstance(item, int):
            msg = "{0} indices must be integers or slices, not {1}"
            raise TypeError(msg.format(self.__class__.__name__,
                                       item.__class__.__name__))
        self.pop(item)

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
            ret_data = datacopy(self._data[index])
            ret_lengths = None
            if self._arity > 1:
                ret_lengths = _get_lenarray_empty(ret_data.shape)
            ret = self._element(
                    _mode="ref",
                    storage="numpy",
                    data_store=ret_data,
                    len_data_store=ret_lengths,
                )
            self._data[index:self._len-1] = self._data[index+1:self._len]
            try:
                self._data[self._len-1] = np.zeros_like(self._data[self._len-1])
            except ValueError: # numpy bug
                for field in self._data.dtype.fields:
                    self._data[self._len-1][field] = np.zeros_like(self._data[self._len-1][field])
            if not self._elementary:
                self._children.pop(index)
            self._del_child_lengths(index)
        elif self._elementary:
            ret = self._data[:self._len][index]
            self._data.__delitem__(index)
        else:
            ret = self._children[:self._len][index].copy()
            self._children.__delitem__(index)
            self._data.__delitem__(index)
        self._len -= 1
        return ret

    def __iter__(self, *args, **kwargs):
        if self._elementary:
            return self._data[:self._len].__iter__(*args, **kwargs)
        else:
            return self._children[:self._len].__iter__(*args, **kwargs)

    def _Len__(self):
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
        self.insert(self._len, item)

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
                child_data = self._element(item).make_numpy()
                child_lengths = None
                if self._arity > 1:
                    child_data, child_lengths = child_data
                self._data[index+1:self._len+1] = self._data[index:self._len]
                if self._arity > 1:
                    slices = [slice(0,v) for v in child_data.shape]
                    self._data[index][slices] = child_data
                else:
                    self._data[index] = child_data
                self._insert_child_lengths(index, child_lengths)
                child = self._element (
                    _mode="parent",
                    parent=self,
                    storage="numpy",
                    data_store=self._data[index],
                    len_data_store=self._get_child_lengths(index),
                )
                self._children.insert(index, child)
                for n in range(index, self._len):
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
                      len_data_store=self._get_child_lengths(index)
                    )
                    self._children.insert(index, child)
                    child.set(item)

    def __eq__(self, other):
        if self.storage == other.storage == "json":
            return self._data == other._data

        else: #can't use numpy data because of PTR
            return self.json() == other.json()

    def __len__(self):
        return self._len

    def _clear_data(self):
        data = self._data
        if self.storage == "numpy":
            data[:] = np.zeros_like(data)
        else:
            for child in self._children:
                child._clear_data()
