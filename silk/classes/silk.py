import numpy as np
import weakref
import copy
from collections import Iterable, OrderedDict

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
 _get_numpy_ele_prop, _filter_json, datacopy, _update_ptr


class SilkOrderedDict(OrderedDict):

    def __repr__(self):
        return dict.__repr__(self)


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
            self._init(kwargs["parent"], kwargs["storage"], kwargs["data"], rebind=False)

        else:
            assert "parent" not in kwargs
            assert "storage" not in kwargs
            assert "data_store" not in kwargs
            self._init(None, "json", None, rebind=False)

            if _mode == "any":
                self.set(*args, **kwargs)

            elif _mode == "from_json":
                self.set(*args, prop_setter=_prop_setter_json, **kwargs)

            elif _mode == "empty":
                pass

            else:
                raise ValueError(_mode)

    def _restore_array_coupling(self):
        for childname, child in self._children.items():
            child._restore_array_coupling()

    def _fix_numpy_ref(self):
        from .silkarray import SilkArray
        for name, prop_data in self._props.items():
            if prop_data["elementary"]:
                continue

            if prop_data["optional"]:
                self._children[name]._is_none = (not self._data["HAS_"+name])

            else:
                self._children[name]._is_none = False

    def _init(self, parent, storage, data_store, rebind):
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

        if not rebind:
            self._children = {}
            self._is_none = False
            self._storage_nonjson_children.clear()

        for name, prop_data in self._props.items():
            if prop_data["elementary"]:
                continue

            if "typeclass" in prop_data:
                type_class = prop_data["typeclass"]

            else:
                typename = prop_data["typename"]
                type_class = typenames._silk_types[typename]

            if self.storage == "json":
                if name not in data_store:
                    if issubclass(type_class, SilkArray):
                        data_store[name] = []

                    else:
                        data_store[name] = {}

            elif self.storage == "numpy":
                if rebind:
                    child = self._children[name]
                    assert child.storage == "numpy"
                    child._data = data_store[name]

            else:
                raise ValueError(self.storage)

            if not rebind:
                c_data_store = data_store[name]
                l_data_store = None
                storage = self.storage
                if self.storage == "numpy" and issubclass(type_class, SilkArray):
                    l_data_store = datacopy(data_store["LEN_" + name])

                self._children[name] = type_class(_mode="parent", storage=storage, parent=self, data_store=c_data_store,
                                                  len_data_store=l_data_store)
        self._data = data_store

    def copy(self, storage="json"):
        """Returns a copy with the storage in the specified format"""
        cls = type(self)
        if storage == "json":
            json = self.json()
            ret = cls.from_json(json)
            for name, prop_data in self._props:
                if not prop_data["elementary"]:
                    child = self._children[name]
                    is_none = child._is_none
                    ret._children[name]._is_none = is_none

        elif storage == "numpy":
            numpy_data = self.numpy()
            ret = cls.from_numpy(numpy_data, copy=False)

            for prop in self._children:
                child = ret._children[prop]
                is_none = child._is_none
                ret._children[prop]._is_none = is_none

        else:
            raise ValueError(storage)

        return ret

    @classmethod
    def from_json(cls, data):
        data = _filter_json(data)
        return cls(data, _mode="from_json")

    @classmethod
    def from_numpy(cls, data, copy=True,validate=True):
        """Constructs from a numpy array singleton "data"
        """
        if data.shape != ():
            raise TypeError("Data must be a singleton")

        if data.dtype != np.dtype(cls._dtype, align=True):
            raise TypeError("Data has the wrong dtype")

        if copy:
            data = datacopy(data)

        self = cls(_mode="ref", storage="numpy", data_store=data)
        if validate:
            self.validate()

        return self

    @classmethod
    def empty(cls):
        return cls(_mode="empty")

    def set(self, *args, prop_setter=_prop_setter_any, **kwargs):
        if len(args) == 1 and not kwargs:
            if args[0] is None or isinstance(args[0], SilkObject) and args[0]._is_none:
                self._is_none = True
                self._clear_data()
                return

        # TODO: make a nice composite exception that stores all exceptions
        try:
            self._construct(prop_setter, *args, **kwargs)

        except:
            if len(args) == 1 and not kwargs:
                try:
                    a = args[0]
                    try:
                        if isinstance(a, np.void):
                            d = {}
                            for name in a.dtype.fields:
                                if name.startswith("HAS_"):
                                    continue

                                has_name = "HAS_" + name
                                if has_name in a.dtype.names and not a[has_name]:
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
                        elif isinstance(a, Iterable) or isinstance(a, np.void):
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
        json_data = SilkOrderedDict()

        empty = True
        for prop_name in self._props:
            is_elementary = self._props[prop_name]["elementary"]

            if is_elementary:
                value = self._data[prop_name]
                if value is np.ma.masked:
                    value = None

            else:
                value = self._children[prop_name].json()

            if value is not None:
                json_data[prop_name] = value
                empty = False

        if empty:
            return None

        else:
            return json_data

        """Returns a JSON representation of the Silk object
        """
        if self.storage == "json":
            return _filter_json(self._data)

        json_dict = {}
        for name, prop_data in self._props.items():
            is_elementary = prop_data["elementary"]
            value = None
            if is_elementary:
                if self.storage == "numpy":
                    value = _get_numpy_ele_prop(self, name)

                else:
                    value = self._data[name]

                if value is not None:
                    if "typeclass" in prop_data:
                        type_class = prop_data["typeclass"]

                    else:
                        typename = prop_data["typename"]
                        type_class = typenames._silk_types[typename]

                    value = type_class(value)
            else:
                child = self._children[name]
                if not child._is_none:
                    value = child.json()

            if value is not None:
                json_dict[name] = value

        return json_dict

    def numpy(self):
        """Returns a numpy representation of the Silk object
        NOTE: for optional members,
          the entire storage buffer is returned,
          including (zeroed) elements if the data is not present!
          the extra field "HAS_xxx" indicates if the data is present.
        NOTE: for all numpy array members,
          the entire storage buffer is returned,
          including (zeroed) elements if the data is not present!
          the length of each array is stored in the LEN_xxx field
          TODO: document multidimensional length vector, PTR_LEN_xxx
        NOTE: for numpy array members of variable shape,
          an extra field "PTR_xxx" contains a C pointer to the data
          For this, the dimensionality of the array does not matter,
           e.g. both for IntegerArray and IntegerArrayArray,
            the C pointer will be "int *"
           and both for MyStructArray and MyStructArrayArray,
            the C pointer will be "MyStruct *"
        """
        if self.storage == "numpy":
            return datacopy(self._data)

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

            self._init(parent, "json", None, rebind=False)
            self.set(json, prop_setter=_prop_setter_json)

            for prop in self._props:
                if not self._props[prop]["elementary"]:
                    child = old_children[prop] # TODO WHY?

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

    def make_numpy(self, _toplevel=True):
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

        dtype = np.dtype(self._dtype, align=True)
        data = np.zeros(dtype=dtype, shape=(1,))

        for name, prop_data in self._props.items():
            if prop_data["elementary"]:
                value = getattr(self, name)
                _set_numpy_ele_prop(self, name, value, data)

            else:
                child = self._children[name]
                if not child._is_none:
                    child.make_numpy(_toplevel=False)

                    if isinstance(child, SilkArray):
                        if prop_data.get("var_array", False):
                            data[0][name] = child._data.copy()
                            child._data = data[0][name]

                            data[0]["LEN_"+name] = child._Len.copy()
                            child._Len = data[0]["LEN_"+name]

                        else:
                            data[0][name] = np.zeros_like(dtype[name])
                            slices = [slice(0, v) for v in child._data.shape]
                            data[0][name][slices] = child._data
                    else:
                        data[0][name] = child._data
                else:
                    type_class = type(child)
                    self._children[name] = type_class.from_numpy(data[0][name], copy=False)
                    self._children[name]._is_none = True

        self._init(self._parent(), "numpy", data[0], rebind=True)

        parent = self._parent()
        if parent is not None:
            if parent.storage != "numpy":
                parent._add_nonjson_child(self)

        if _toplevel:
            self._restore_array_coupling()

        return data[0]

    def _find_child(self, child_id):
        for name, child_data in self._children.items():
            if child_id == id(child_data):
                return name

        raise KeyError

    def _add_nonjson_child(self, child):
        child_name = self._find_child(id(child))
        if self._props[child_name].get("var_array", False) and \
            self.storage == "numpy":
            return

        assert self.storage != "numpy"
        non_json_children = self._storage_nonjson_children
        child_id = id(child)

        if child_id not in non_json_children:
            non_json_children.add(child_id)
            if self.storage == "json":
                self.storage = "mixed"

                parent = self._parent()
                if parent is not None:
                    parent._add_nonjson_child(self)

    def _remove_nonjson_child(self, child):
        assert self.storage != "numpy"
        non_json_children = self._storage_nonjson_children
        child_id = id(child)
        if child_id in non_json_children:
            assert self.storage == "mixed", self.storage
            non_json_children.remove(child_id)

            if not non_json_children:
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
            prop_data = self._props[prop]
            if prop_data["elementary"]:
                value = getattr(self, prop)

                if value is not None:
                    if "typeclass" in prop_data:
                        type_class = prop_data["typeclass"]

                    else:
                        typename = prop_data["typename"]
                        type_class = typenames._silk_types[typename]

                    value = type_class(value)
                data[prop] = value
            else:
                child = self._children[prop]
                copy = datacopy(child._data)
                data[prop] = copy
                child._data = copy

        self._data = data
        self._storage_nonjson_children = set([id(p) for p in self._children.values()])
        self.storage = "mixed"

    def _construct(self, prop_setter, *args, **kwargs):
        prop_data = {}

        if len(args) > len(self._positional_args):
            message = "{0}() takes {1} positional arguments but {2} were given"\
                .format(self.__class__.__name__, len(self._positional_args), len(args))
            raise TypeError(message)

        for i, arg_value in enumerate(args):
            prop_data[self._positional_args[i]] = arg_value

        for arg_name, arg_value in kwargs.items():
            if arg_name in prop_data:
                message = "{0}() got multiple values for argument '{1}'"
                message = message.format(self.__class__.__name__, arg_name)
                raise TypeError(message)

            prop_data[arg_name] = arg_value

        missing = [p for p in self._props if p not in prop_data]
        missing_required = [p for p in missing if not self._props[p]["optional"] and p not in self._props_init]

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
                    ", and" + missing_required[-1]

            message = "{0}() missing {1} positional argument{2}: {3}"\
                .format(self.__class__.__name__, len(missing_required), plural, missing_txt)
            raise TypeError(message)

        for prop_name in self._props:
            value = prop_data.get(prop_name, None)
            if value is None and prop_name in self._props_init:
                value = self._props_init[prop_name]

            self._set_prop(prop_name, value, prop_setter)

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
        return dir(type(self)) #Eh?

    def __setattr__(self, attr, value):
        if attr.startswith("_") or attr == "storage":
            object.__setattr__(self, attr, value)

        else:
            self._set_prop(attr, value, _prop_setter_any)

    def _set_prop(self, prop, value, child_prop_setter):
        try:
            prop_data = self._props[prop]

        except KeyError:
            raise AttributeError(prop)

        if value is None and not prop_data["optional"]:
            raise TypeError("'%s' cannot be None" % prop)

        is_elementary = prop_data["elementary"]

        if is_elementary:
            if self.storage == "numpy":
                _set_numpy_ele_prop(self, prop, value)

            else:
                if value is not None:
                    if "typeclass" in prop_data:
                        type_class = prop_data["typeclass"]

                    else:
                        typename = prop_data["typename"]
                        type_class = typenames._silk_types[typename]

                    value = type_class(value)
                self._data[prop] = value
        else:
            child = self._children[prop]
            if self.storage == "numpy" and prop_data.get("var_array", False):
                child.set(value)

            else:
                child_prop_setter(child, value)

            if self.storage == "numpy" and prop_data["optional"]:
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
            prop_data = self._props[attr]
        except KeyError:
            raise AttributeError(attr) from None

        is_elementary = prop_data["elementary"]

        if is_elementary:
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

    # TODO cleanup
    def _print(self, spaces):
        ret = "{0} (\n".format(self.__class__.__name__)

        for name, prop_data in self._props.items():
            value = getattr(self, name)

            if prop_data["optional"]:
                if value is None:
                    continue

            if self.storage == "numpy" and prop_data["elementary"]:
                if self._data[name].dtype.kind == 'S':
                    substring = '"' + value + '"' # TODO can use repr()?
                else:
                    substring = str(value)

            else:
                substring = value._print(spaces+2)

            ret += "{0}{1} = {2},\n".format(" " * (spaces+2), name, substring)

        ret += "{0})".format(" " * spaces)

        return ret

    def __str__(self):
        return self._print(0)

    def __repr__(self):
        return self._print(0)

    def __eq__(self, other):
        if self.storage == other.storage == "json":
            return self._data == other._data

        else: #can't use numpy data because of PTR
            return self.json() == other.json()

    def _clear_data(self):
        data = self._data
        if self.storage == "numpy":
            data.fill(np.zeros_like(data))

        else:
            for name, prop_data in self._props.items():
                if prop_data["elementary"]:
                    if name in data:
                        data.pop(name)

                else:
                    child = self._children[name]
                    child._clear_data()
