import numpy as np
import weakref
import copy
import collections

# TODO
# - composite exception for constructor
# - (re)alloc numpy; only if parent is json/mixed (or option "force")!!
# - enum
# - composite
# - resources
# elsewhere: xml/json conversion, depsgraph/namespace
# finally: registrar, cell depsgraph

from ..registers import typenames
from . import SilkObject

from .helpers import _prop_setter_any, _prop_setter_json, _set_numpy_ele_prop,\
 _get_numpy_ele_prop

class Silk(SilkObject):
    _props = None
    _dtype = None
    _positional_args = None
    __slots__ = (
        "_parent", "_storage_enum", "_storage_nonjson_children",
        "_data", "_children",
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
                self.set(*args, **kwargs)
            elif _mode == "empty":
                pass
            elif _mode == "from_json":
                self.set(*args, prop_setter=_prop_setter_json, **kwargs)
            else:
                raise ValueError(_mode)

    def _init(self, parent, storage, data_store):
        from .silkarray import SilkArray
        if parent is not None:
            self._parent = weakref.ref(parent)
        else:
            self._parent = lambda: None
        self.storage = storage
        if storage == "json":
            if data_store is None:
                data_store = {}
        elif storage == "numpy":
            assert data_store is not None
            assert data_store.dtype == self._dtype
            assert data_store.shape == ()
        else:
            raise ValueError(storage)

        self._children = {}
        self._storage_nonjson_children.clear()
        for pname, p in self._props.items():
            if p["elementary"]:
                continue
            typename = p["typename"]
            t = typenames._silk_types[typename]
            if self.storage == "json":
                if pname not in data_store:
                    if issubclass(t, SilkArray):
                        data_store[pname] = []
                    else:
                        data_store[pname] = {}
            elif self.storage == "numpy":
                pass
            else:
                raise ValueError(self.storage)
            self._children[pname] = t(
              _mode="parent",
              storage=self.storage,
              parent=self,
              data_store=data_store[pname]
            )
        self._data = data_store

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
            return cls(_mode="ref", storage="json", data_store=data)
        else:
            return cls(data, _mode="from_json")

    @classmethod
    def from_numpy(cls, data, copy=True, lengths=None, validate=True):
        """Constructs from a numpy array singleton "data"
        "lengths": The lengths of the SilkArray members
          If specified, "lengths" must either be a Silk object of type "cls",
            or a nested tuple returned by a Silk._get_lengths() call
          If not specified, it is assumed that "arr" is unpadded,
            i.e. that all elements in SilkArray members have a valid value
        """
        if data.shape != ():
            raise TypeError("Data must be a singleton")
        if data.dtype != self._dtype:
            raise TypeError("Data has the wrong dtype")

        if copy:
            data = data.copy()
        ret = cls(_mode="ref", storage="numpy", data_store=data)
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

    def set(self, *args, prop_setter=_prop_setter_any, **kwargs):
        # TODO: make a nice composite exception that stores all exceptions
        try:
            self._construct(prop_setter, *args, **kwargs)
        except:
            if len(args) == 1 and len(kwargs) == 0:
                try:
                    a = args[0]
                    if isinstance(a, dict):
                        self._construct(prop_setter, **a)
                    elif isinstance(a, str):
                        self._parse(a)
                    elif isinstance(a, collections.Iterable) or isinstance(a, np.void):
                        self._construct(prop_setter, *a)
                    elif isinstance(a, SilkObject):
                        d = {prop: getattr(a, prop) for prop in dir(a)}
                        self._construct(prop_setter, **d)
                    elif hasattr(a, "__dict__"):
                        self._construct(prop_setter, **a.__dict__)
                    else:
                        raise TypeError(a)
                except:
                    raise
            else:
                raise
        self.validate()

    def validate(self):
        pass  # overridden during registration

    def json(self):
        if self.storage == "json":
            return copy.deepcopy(self._data)

        d = {}
        empty = True
        for attr in self._props:
            ele = self._props[attr]["elementary"]
            if ele:
                ret = self._data[attr]
                if ret is np.ma.masked:
                    ret = None
            else:
                ret = self._children[attr].json()
            if ret is not None:
                d[attr] = ret
                empty = False
        if empty:
            return None
        else:
            return d

    def numpy(self):
        """Returns a numpy representation of the Silk object
        NOTE: for Silk array members, the entire storage buffer is returned,
         including (zeroed) elements beyond the current length!
        """
        cls = type(self)
        if self.storage == "numpy":
            new_data = self._data.copy()
        else:
            prop_setter = _prop_setter_any
            if self.storage == "json":
                prop_setter = _prop_setter_json
            my_data = copy.deepcopy(self._data)
            new_data = np.zeros(dtype=self._dtype, shape=(1,))
            new_obj = cls(mode="parent",
                          parent=None, storage="numpy", data_store=new_data[0]
                          )
            for prop, value in my_data.items():
                new_obj._set_prop(prop, value, prop_setter)
        return new_obj._data

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

        prop_setter = _prop_setter_any
        if self.storage == "json":
            prop_setter = _prop_setter_json
        old_data = copy.deepcopy(self._data)
        data = np.zeros(dtype=self._dtype, shape=(1,))
        self._init(self._parent(), "numpy", data[0])
        for prop, value in old_data.items():
            self._set_prop(prop, value, prop_setter)
        parent = self._parent()
        if parent is not None:
            parent()._add_nonjson_child(self)
        return self._data

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
        ret = {}
        for childname, child in self._children.items():
            child_lengths = child._get_lengths()
            if child_lengths is not None:
                ret[childname] = child_lengths
        if not len(ret):
            return None
        else:
            return ret

    def _set_lengths_from_data(self):
        assert self.storage == "numpy"
        for childname in self._children:
            child = self._children[childname]
            child._set_lengths_from_data()

    def _set_lengths(self, lengths):
        assert self.storage == "numpy"
        assert isinstance(lengths, dict), type(lengths)
        for childname in self._children:
            if childname not in lengths:
                continue
            child = self._children[childname]
            child._set_lengths(lengths[childname])

    def _construct(self, prop_setter, *args, **kwargs):
        propdict = {}
        if len(args) > len(self._positional_args):
            message = "{0}() takes {1} positional arguments \
but {2} were given".format(
              self.__class__.__name__,
              len(self._positional_args),
              len(args)
            )
            raise TypeError(message)
        for anr, a in enumerate(args):
            propdict[self._positional_args[anr]] = a
        for argname, a in kwargs.items():
            if argname in propdict:
                message = "{0}() got multiple values for argument '{1}'"
                message = message.format(
                  self.__class__.__name__,
                  argname
                )
                raise TypeError(message)
            propdict[argname] = a
        missing = [p for p in self._props if p not in propdict]
        missing_required = [p for p in missing
                            if not self._props[p]["optional"]
                            and p not in self._props_init]
        if missing_required:
            missing_required = ["'{0}'".format(p) for p in missing_required]
            if len(missing_required) == 1:
                plural = ""
                missing_txt = missing_required[0]
            elif len(missing_required) == 2:
                plural = "s"
                missing_txt = missing_required[0] + " and " + \
                    missing_required[1]
            else:
                plural = "s"
                missing_txt = ", ".join(missing_required[:-1]) + \
                    ", and " + missing_required[-1]
            message = "{0}() missing {1} positional argument{2}: {3}".format(
              self.__class__.__name__,
              len(missing_required),
              plural,
              missing_txt
            )
            raise TypeError(message)

        for propname in self._props:
            value = propdict.get(propname, None)
            if value is None and propname in self._props_init:
                value = self._props_init[propname]
            self._set_prop(propname, value, prop_setter)

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

    def _set_prop(self, prop, value, child_prop_setter):
        try:
            ele = self._props[prop]["elementary"]
        except KeyError:
            raise AttributeError(prop)
        if ele:
            if self.storage == "numpy":
                _set_numpy_ele_prop(self, prop, value)
            else:
                typename = \
                  self._props[prop]["typename"]
                t = typenames._silk_types[typename]
                value = t(value)
                self._data[prop] = value
        else:
            child_prop_setter(self._children[prop], value)

    def __getattribute__(self, attr):
        value = object.__getattribute__(self, attr)
        if attr.startswith("_") or attr == "storage":
            return value
        class_value = getattr(type(self), attr)
        if value is class_value:
            raise AttributeError(value)
        return value

    def __getattr__(self, attr):
        try:
            ele = self._props[attr]["elementary"]
        except KeyError:
            raise AttributeError(attr)
        if ele:
            if self.storage == "numpy":
                ret = _get_numpy_ele_prop(self, attr)
            else:
                ret = self._data[attr]
        else:
            ret = self._children[attr]

        if ret is np.ma.masked:
            return None
        else:
            return ret

    def _print(self, spaces):
        ret = "{0} (\n".format(self.__class__.__name__)
        for propname in self._props:
            prop = self._props[propname]
            value = getattr(self, propname)
            if prop["optional"]:
                if value is None:
                    continue
            if self.storage == "numpy" and prop["elementary"]:
                if value.dtype.kind == 'S':
                    substr = '"' + value.decode() + '"'
                else:
                    substr = str(value)
            else:
                substr = value._print(spaces+2)
            ret += "{0}{1} = {2},\n".format(" " * (spaces+2), propname, substr)
        ret += "{0})".format(" " * spaces)
        return ret

    def __str__(self):
        return self._print(0)

    def __repr__(self):
        return self._print(0)

    def __eq__(self, other):
        if self.storage == other.storage:
            return self._data == other._data
        else:
            return self.json() == other.json()
