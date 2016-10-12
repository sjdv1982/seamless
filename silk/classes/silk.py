import numpy as np
import weakref
import copy
import collections

# TODO
# - composite exception for constructor
# - resources (new class generated as _silk_types['ResourceX'], where X is name of Silk class)
# elsewhere:
#  - update bracketlength macro:
#         XArray[spam][eggs] => maxshape = (spam, eggs) AND validate/hardform
#         XArray[:spam][:eggs] => maxshape = (spam, eggs)
#         mixed syntax also allowed
#  - xml/json conversion,
#  - depsgraph/namespace
# finally: registrar, cell depsgraph

from ..registers import typenames
from . import SilkObject

from .helpers import _prop_setter_any, _prop_setter_json, _set_numpy_ele_prop,\
 _get_numpy_ele_prop, _filter_json

class Silk(SilkObject):
    _anonymous = None           # bool
    _props = None               # list
    _dtype = None               # list
    _positional_args = None     # list
    __slots__ = [
        "_parent", "_storage_enum", "_storage_nonjson_children",
        "_data", "_children", "_is_none", "__weakref__"
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
            assert "parent" not in kwargs
            self._init(
                None,
                kwargs["storage"],
                kwargs["data_store"],
            )
        else:
            assert "parent" not in kwargs
            assert "storage" not in kwargs
            assert "data_store" not in kwargs
            self._init(None, "json", None)
            if _mode == "any":
                self.set(*args, **kwargs)
            elif _mode == "empty":
                pass
            elif _mode == "from_json":
                self.set(*args, prop_setter=_prop_setter_json, **kwargs)
            else:
                raise ValueError(_mode)

    def _numpy_bind(self, data_store):
        self.storage = "numpy"
        assert data_store.dtype == np.dtype(self._dtype, align=True)
        assert data_store.shape == ()
        self._data = data_store
        for childname, child in self._children.items():
            child._numpy_bind(data_store[childname])
        parent = self._parent()
        if parent is not None and parent.storage != "numpy":
            parent._add_nonjson_child(self)

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
            assert data_store.dtype == np.dtype(self._dtype, align=True)
            assert data_store.shape == ()
        else:
            raise ValueError(storage)

        self._children = {}
        self._is_none = False
        self._storage_nonjson_children.clear()
        for pname, p in self._props.items():
            if p["elementary"]:
                continue
            if "typeclass" in p:
                t = p["typeclass"]
            else:
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

            if self.storage == "numpy" and p.get("var_array", False):
                self._children[pname] = t.empty()
                # Will be converted to numpy representation when the value is set
            else:
                self._children[pname] = t(
                  _mode="parent",
                  storage=self.storage,
                  parent=self,
                  data_store=data_store[pname]
                )
        self._data = data_store

    def copy(self, storage="json"):
        """Returns a copy with the storage in the specified format"""
        cls = type(self)
        if storage == "json":
            json = self.json()
            ret = cls.from_json(json, copy=False)
            for prop in self._props:
                if not self._props[prop]["elementary"]:
                    child = self._children[prop]
                    is_none = child._is_none
                    ret._children[prop]._is_none = is_none
        elif storage == "numpy":
            numpydata = self.numpy()
            ret = cls.from_numpy(numpydata, copy=False)
            for prop, value in self._data.items():
                if prop in self._children:
                    child = ret._children[prop]
                    is_none = child._is_none
                    ret._children[prop]._is_none = is_none
        else:
            raise ValueError(storage)
        return ret

    @classmethod
    def from_json(cls, data, copy=True):
        if not copy:
            return cls(_mode="ref", storage="json", data_store=data)
        else:
            data = _filter_json(data)
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
        if len(args) == 1 and len(kwargs) == 0:
            if args[0] is None or isinstance(args[0], SilkObject) and args[0]._is_none:
                self._is_none = True
                if self.storage == "numpy":
                    self._data.fill(np.zeros_like(self._data))
                return

        # TODO: make a nice composite exception that stores all exceptions
        try:
            self._construct(prop_setter, *args, **kwargs)
        except:
            if len(args) == 1 and len(kwargs) == 0:
                try:
                    a = args[0]
                    try:
                        if isinstance(a, np.void):
                            d = {}
                            for name in a.dtype.names:
                                if name.startswith("HAS_"):
                                    continue
                                name2 = "HAS_" + name
                                if name2 in a.dtype.names and not a[name2]:
                                    continue
                                d[name] = a[name]
                            self._construct(prop_setter, **d)
                        else:
                            raise TypeError
                    except:
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
        self._is_none = False

    def validate(self):
        pass  # overridden during registration

    def json(self):
        """Returns a JSON representation of the Silk object
        NOTE: for optional members,
        the entire storage buffer is returned,
         including (zeroed/empty) elements beyond the defined data!
        """
        if self.storage == "json":
            return copy.deepcopy(self._data)

        d = {}
        for attr in self._props:
            p = self._props[attr]
            ele = p["elementary"]
            if ele:
                if self.storage == "numpy":
                    value = _get_numpy_ele_prop(self, attr)
                else:
                    value = self._data[attr]
                if value is not None:
                    if "typeclass" in p:
                        t = p["typeclass"]
                    else:
                        typename = p["typename"]
                        t = typenames._silk_types[typename]
                    value = t(value)
            else:
                value = self._children[attr].json()
            if value is not None:
                d[attr] = value
        return d

    def numpy(self):
        """Returns a numpy representation of the Silk object
        NOTE: for optional members,
          the entire storage buffer is returned,
          including (zeroed) elements if the data is not present!
          the extra field "HAS_xxx" indicates if the data is present.
        NOTE: for all numpy array members,
          the entire storage buffer is returned,
          including (zeroed) elements if the data is not present!
          the length of each array is not stored, and must be obtained
           from the original SilkArray object
        NOTE: for numpy array members of variable shape,
          an extra field "PTR_xxx" contains a C pointer to the data
          For this, the dimensionality of the array does not matter,
           e.g. both for IntegerArray and IntegerArrayArray,
            the C pointer will be "int *"
           and both for MyStructArray and MyStructArrayArray,
            the C pointer will be "MyStruct *"
        """
        if self.storage == "numpy":
            return self._data.copy()
        new_obj = self.copy("json")
        return new_obj.make_numpy()

    def make_json(self):
        if self.storage == "json":
            return self._data
        elif self.storage == "numpy":
            old_children = self._children
            json = _filter_json(self.json(), self)
            parent = self._parent()
            if parent is not None and parent.storage == "numpy":
                parent.numpy_shatter()
            self._init(parent, "json", None)
            self.set(json, prop_setter=_prop_setter_json)
            for prop in self._props:
                if not self._props[prop]["elementary"]:
                    child = old_children[prop]
            if parent is not None:
                parent._remove_nonjson_child(self)
                myname = parent._find_child(id(self))
                parent._data[myname] = self._data
            return self._data
        elif self.storage == "mixed":
            for child_id in list(self._storage_nonjson_children):  # copy!
                for child in self._children.values():
                    if id(child) == child_id:
                        child.make_json()
                        break
                else:
                    raise Exception("Cannot find child that was marked as 'non-JSON'")
            # Above will automatically update storage status to "json"
            return self._data

    def make_numpy(self):
        """Sets the internal storage to 'numpy'
        Returns the numpy array that is used as internal storage buffer
        NOTE: for optional members,
          the entire storage buffer is returned,
          including (zeroed) elements if the data is not present!
          an extra field "HAS_xxx" indicates if the data is present.
        NOTE: for all numpy array members,
          the entire storage buffer is returned,
          including (zeroed) elements if the data is not present!
          the length/shape of each array is not stored, and must be obtained
           from the original SilkArray object
        NOTE: for numpy array members of variable shape,
          an extra field "PTR_xxx" contains a C pointer to the data
          For this, the dimensionality of the array does not matter,
           e.g. both for IntegerArray and IntegerArrayArray,
            the C pointer will be "int *"
           and both for MyStructArray and MyStructArrayArray,
            the C pointer will be "MyStruct *"
        """
        if self.storage == "numpy":
            return self._data

        dtype = np.dtype(self._dtype, align=True)
        data = np.zeros(dtype=dtype, shape=(1,))
        for propname,prop in self._props.items():
            if prop["elementary"]:
                value = getattr(self, propname)
                _set_numpy_ele_prop(self, propname, value, data)
            else:
                child = self._children[propname]
                if not child._is_none:
                    child.make_numpy()
                    data[0][propname] = child._data
        self._numpy_bind(data[0])
        return data

    def _find_child(self, child_id):
        for childname, ch in self._children.items():
            if child_id == id(ch):
                return childname
        raise KeyError

    def _add_nonjson_child(self, child):
        childname = self._find_child(id(child))
        if self._props[childname].get("var_array", False) and \
          self.storage == "numpy":
          return
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
        parent = self._parent()
        if parent is not None and parent.storage == "numpy":
            parent.numpy_shatter()
        data = {}
        for prop in self._props:
            p = self._props[prop]
            if p["elementary"]:
                value = getattr(self, prop)
                if value is not None:
                    if "typeclass" in p:
                        t = p["typeclass"]
                    else:
                        typename = p["typename"]
                        t = typenames._silk_types[typename]
                    value = t(value)
                data[prop] = value
            else:
                child = self._children[prop]
                d = child._data.copy()
                data[prop] = d
                child._data = d
        self._data = data
        self._storage_nonjson_children = set([id(p) for p in self._children.values()])
        self.storage = "mixed"

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
            if self._props[childname].get("var_array", False):
                #the child will still be empty...
                clengths = lengths[childname]
                shape = [len(clengths)]
                l = clengths
                for n in range(1, child._arity):
                    max_len = max([len(d) for d in l])
                    l = sum(l, [])
                data = np.zeros(dtype=child._dtype,shape=shape)
                child._init(self, "numpy", data)
            assert child.storage == "numpy", childname
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
            p = self._props[prop]
        except KeyError:
            raise AttributeError(prop)
        if value is None and not p["optional"]:
            raise TypeError("'%s' cannot be None" % prop)
        ele = p["elementary"]
        if ele:
            if self.storage == "numpy":
                _set_numpy_ele_prop(self, prop, value)
            else:
                if value is not None:
                    if "typeclass" in p:
                        t = p["typeclass"]
                    else:
                        typename = p["typename"]
                        t = typenames._silk_types[typename]
                    value = t(value)
                self._data[prop] = value
        else:
            child = self._children[prop]
            child_prop_setter(child, value)
            if self.storage == "numpy" and p["optional"]:
                self._data["HAS_"+prop] = (value is not None)


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
            raise AttributeError(attr) from None
        if ele:
            if self.storage == "numpy":
                ret = _get_numpy_ele_prop(self, attr)
            else:
                ret = self._data.get(attr, None)
                if ret is None:
                    assert self._props[attr]["optional"]
        else:
            ret = self._children[attr]
            if ret._is_none:
                ret = None
        return ret

    def _print(self, spaces):
        name = ""
        if not self._anonymous:
            name = self.__class__.__name__ + " "
        ret = "{0}(\n".format(name)
        for propname in self._props:
            prop = self._props[propname]
            value = getattr(self, propname)
            if prop["optional"]:
                if value is None:
                    continue
            if self.storage == "numpy" and prop["elementary"]:
                substr = value
                if self._data[propname].dtype.kind == 'S':
                    substr = '"' + value + '"'
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
