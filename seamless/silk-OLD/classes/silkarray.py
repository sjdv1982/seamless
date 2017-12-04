import numpy as np
import weakref
import copy
import collections
from weakref import WeakValueDictionary
from .helpers import _get_lenarray_full, _get_lenarray_empty, _get_lenarray_size, _lenarray_copypad

from . import SilkObject

from .helpers import _prop_setter_any, _prop_setter_json, \
    _set_numpy_ele_prop, _set_numpy_ele_range, _get_numpy_ele_prop, \
    _filter_json, datacopy

class _ArrayConstructContext:
    def __init__(self, arr):
        self.arr = arr

    def __enter__(self):
        self.old_data = self.arr._data[:]
        if self.arr.storage != "numpy":
            self.old_children = self.arr._children[:]

    def __exit__(self, type, value, traceback):
        if type is not None:
            self.arr._data[:] = self.old_data
            if self.arr.storage != "numpy":
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
            dtype = np.dtype(self.arr.dtype, align=True)
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
    dtype = None
    _elementary = None
    _arity = None
    __slots__ = [
        "_parent", "_storage_enum", "_storage_nonjson_children",
        "_data", "_children", "_Len", "_is_none", "__weakref__"
    ]

    def __init__(self, *args, _mode="any", **kwargs):
        self._storage_enum = None
        self._storage_nonjson_children = set()
        self._children = None
        if _mode == "parent":
            self._init(
                kwargs["parent"],
                kwargs["storage"],
                kwargs["data_store"],
                kwargs["len_data_store"],
            )
        elif _mode == "from_numpy":
            assert "parent" not in kwargs
            self._init(
                None,
                "numpy",
                kwargs["data_store"],
                kwargs["len_data_store"],
            )
        else:
            assert "parent" not in kwargs
            assert "storage" not in kwargs
            assert "data_store" not in kwargs
            self._init(None, "json", None, None)
            if _mode == "any":
                self.set(*args)
            elif _mode == "empty":
                pass
            elif _mode == "from_json":
                self.set(*args, prop_setter=_prop_setter_json, **kwargs)
            else:
                raise ValueError(_mode)

    @property
    def _len(self):
        return int(self._Len[0])

    @_len.setter
    def _len(self, value):
        self._Len[0] = value

    def _init(self, parent, storage, data_store, len_data_store):
        if parent is not None:
            if storage == "numpy":
                self._parent = lambda: parent # hard ref
            else:
                self._parent = weakref.ref(parent)
        else:
            self._parent = lambda: None
        self.storage = storage

        self._is_none = False
        self._storage_nonjson_children.clear()

        if self._children is not None:
            for child in self._children:
                child._parent = lambda: None
        if storage == "json":
            self._children = []
            if data_store is None:
                data_store = []
            self._data = data_store
            self._Len = [0]
        elif storage == "numpy":
            self._children = WeakValueDictionary()
            assert data_store is not None
            assert len_data_store is not None
            assert len(len_data_store), len_data_store
            dtype = np.dtype(self.dtype, align=True)
            assert data_store.dtype == dtype
            self._data = data_store
            self._Len = len_data_store
            return
        else:
            raise ValueError(storage)

        assert storage == "json"
        for n in range(len(self._data)):
            if n > len(data_store):
                if issubclass(self._element, SilkArray):
                    self._data.append([])
                else:
                    self._data.append({})
            if not self._elementary:
                child = self._element(
                  _mode="parent",
                  storage="json",
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
            numpydata = self.numpy()
            lengths = self.lengths()
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
        if arr.dtype != np.dtype(cls.dtype,align=True):
            raise TypeError("Array has the wrong dtype")
        if lengths is None and length_can_be_none:
            return
        assert lengths.dtype == np.uint32
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
        ret = cls(_mode="from_numpy", data_store=arr,len_data_store=lengths)
        if validate:
            ret.validate()
        return ret

    @classmethod
    def empty(cls):
        return cls(_mode="empty")

    def _get_child(self, childnr):
        if not isinstance(childnr, int):
            raise TypeError(childnr)
        if childnr < 0:
            childnr += self._len
        if childnr < 0 or childnr >= self._len:
            raise IndexError(childnr)
        from .silkarray import SilkArray
        if self.storage == "numpy":
            child = self._element (
                _mode = "parent",
                parent = self,
                storage = "numpy",
                data_store = self._data[childnr],
                len_data_store = self._get_child_lengths(childnr)
            )
            self._children[childnr] = child
        return self._children[childnr]

    def _get_children(self):
        if self.storage == "numpy":
            for n in range(self._len):
                yield self._get_child(n)
        else:
            for child in self._children:
                yield child

    def set(self, *args, prop_setter=_prop_setter_any):
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
                self._construct_from_numpy(args[0],lengths=None)
            else:
                raise TypeError("Not a numpy array")
        except Exception:
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
            except Exception:
                if not ok:
                    if not keep_trying:
                        raise
                    try:
                        self._construct(prop_setter, *args)
                    except Exception:
                        raise
        self.validate()
        self._is_none = False

    def validate(self):
        pass

    def json(self):
        """Returns a JSON representation of the Silk object
        """
        if self.storage == "json":
            return _filter_json(self._data)

        if self._elementary:
            return [dd for dd in self._data]
        else:
            d = []
            for child in self._get_children():
                dd = child.json()
                d.append(dd)
        return d

    def numpy(self):
        """Returns a numpy representation of the Silk object
        NOTE: for all numpy arrays,
          the entire storage buffer is returned,
          including (zeroed) elements if the data is not present!
          the length of each array is stored in the LEN_xxx field
          TODO: document multidimensional length vector, PTR_LEN_xxx
        TODO: add and document SHAPE field
        """
        if self.storage == "numpy":
            return datacopy(self._data)
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
            self._init(parent, "json", None, None)
            self.set(json, prop_setter=_prop_setter_json)
            if parent is not None:
                parent._remove_nonjson_child(self)
                myname = parent._find_child(id(self))
                parent._data[myname] = self._data
            return self._data
        elif self.storage == "mixed":
            for child_id in list(self._storage_nonjson_children):  # copy!
                for child in self._get_children():
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
            maxlen = max([len(dd) for dd in d])
            shape.append(maxlen)
            d2 = []
            for dd in d:
                for ddd in dd:
                    d2.append(ddd)
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

    def _restore_array_coupling(self, data=None, myname=None):
        """
        Array members have their length vector stored in the parent data
        In addition, var_arrays have a pointer to their data stored
        If the parent data gets reallocated or copied, then
         this information gets decoupled, so it must be restored
        """
        assert self.storage == "numpy"
        if data is None:
            parent = self._parent()
            if parent is None:
                return
            if parent.storage != "numpy":
                return
            myname = parent._find_child(id(self))
            if not isinstance(parent, SilkArray) and \
              parent._props[myname].get("var_array", False):
                data = parent._data
                assert data is not None
        if data is not None:
            assert myname is not None
            data[myname] = self._data
            data["PTR_"+myname] = self._data.ctypes.data
            data["LEN_"+myname] = self._Len.copy()
            self._Len = data["LEN_"+myname]
            if self._arity > 1:
                data["SHAPE_"+myname] = self._data.shape
                data["PTR_LEN_"+myname] = self._Len.ctypes.data


    def make_numpy(self,_toplevel=None):
        """Sets the internal storage to 'numpy'
        Returns the numpy array that is used as internal storage buffer
        NOTE: for optional members,
          the entire storage buffer is returned,
          including (zeroed) elements if the data is not present!
          an extra field "HAS_xxx" indicates if the data is present.
        TODO: update doc
        NOTE: for numpy array members of variable shape,
          an extra field "PTR_xxx" contains a C pointer to the data
          For this, the dimensionality of the array does not matter,
           e.g. both for IntegerArray and IntegerArrayArray,
            the C pointer will be "int *"
           and both for MyStructArray and MyStructArrayArray,
            the C pointer will be "MyStruct *"
        """
        from .silkarray import SilkArray
        if self.storage == "numpy":
            return self._data

        dtype = np.dtype(self.dtype, align=True)
        shape = self._get_outer_shape()
        data = np.zeros(dtype=dtype, shape=shape)
        lengths = _get_lenarray_empty(shape)
        lengths[0] = len(self)
        if self._elementary:
            self._set_numpy_ele_range(self, 0, len(self._data), self._data, self._arity, data)
        else:
            for childnr, child in enumerate(self._get_children()):
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

        self._init(self._parent(), "numpy", data, lengths)
        parent = self._parent()
        if parent is not None:
            if parent.storage != "numpy":
                parent._add_nonjson_child(self)
        for child in self._get_children():
            child._restore_array_coupling()

        return data

    def lengths(self):
        assert self.storage == "numpy"
        return self._Len

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
        self._data = np.zeros(dtype=self.dtype, shape=shape)
        slices = [slice(0,s) for s in min_shape]
        self._data[slices] = old_data
        self._Len = _get_lenarray_empty(shape)
        _lenarray_copypad(self._Len, shape, old_len, old_data.shape)
        self._init(parent, "numpy", self._data, self._Len)
        self._restore_array_coupling()

    def _find_child(self, child_id):
        if self.storage == "numpy":
            for childname, ch in self._children.items():
                if child_id == id(ch):
                    return childname
        else:
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
                    parent()._remove_nonjson_child(self)


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
        children = []
        for child in self._get_children():
            d = datacopy(child._data)
            data.append(d)
            child._data = d
            children.append(child)
        self._data = data
        self._children = children
        self._storage_nonjson_children = set([id(p) for p in children])
        self.storage = "mixed"

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
                        child = self._get_child(anr)
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

    def _construct_from_numpy(self, arr, lengths):
        if self.storage != "numpy":
            self._init(self._parent(), "numpy", arr, lengths)
            self.make_json()
            return

        self._check_numpy_args(arr, lengths, self_data=self._data, length_can_be_none=False)
        if lengths is None:
            lengths = _get_lenarray_full(arr.shape)

        self._data = datacopy(arr)
        self._Len = lengths.copy()
        self._restore_array_coupling()

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

    def __dir__(self):
        return dir(type(self))

    def __setattr__(self, attr, value):
        if attr.startswith("_") or attr == "storage":
            object.__setattr__(self, attr, value)
        else:
            self._set_prop(attr, value, _prop_setter_any)

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
            return self._get_child(item)

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
            child = self._get_child(item)
            child.set(value,prop_setter=prop_setter)

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
                    _mode="from_numpy",
                    data_store=ret_data,
                    len_data_store=ret_lengths,
                )
            self._data[index:self._len-1] = self._data[index+1:self._len]
            try:
                self._data[self._len-1] = np.zeros_like(self._data[self._len-1])
            except ValueError: # numpy bug
                for field in self._data.dtype.fields:
                    self._data[self._len-1][field] = np.zeros_like(self._data[self._len-1][field])
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
                value = self._get_child(n)
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
                ele = self._element(item)
                child_data = ele.make_numpy()
                child_lengths = None
                if self._arity > 1:
                    child_lengths = ele.lengths()
                self._data[index+1:self._len+1] = self._data[index:self._len]
                if self._arity > 1:
                    slices = [slice(0,v) for v in child_data.shape]
                    self._data[index][slices] = child_data
                else:
                    self._data[index] = child_data
                self._insert_child_lengths(index, child_lengths)
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
        if not isinstance(other, SilkArray):
            return False
        if self.storage == other.storage == "json":
            return self._data == other._data
        else: #can't use numpy _data because of PTR and different allocation sizes
            return self.json() == other.json()

    def __len__(self):
        return self._len

    def _clear_data(self):
        d = self._data
        if self.storage == "numpy":
            d[:] =  np.zeros_like(d)
        else:
            for child in self._get_children():
                child._clear_data()
