import numpy as np
from collections import OrderedDict
import weakref

# TODO
# - composite exception for constructor

from ..registers.typenames import _typenames
from . import SilkObject


def _prop_setter_any(child, value): return child.set(value)


def _prop_setter_json(child, value):
    return child.set(value, prop_setter=_prop_setter_json)


class SilkOrderedDict(OrderedDict):

    def __repr__(self):
        return dict.__repr__(self)


class Silk(SilkObject):
    _props = None
    _dtype = None
    _positional_args = None

    __slots__ = (
        "_parent", "_storage_enum",
        "_data", "_children",
    )

    def __init__(self, *args, _mode="any", **kwargs):
        self._storage_enum = None

        if _mode == "parent":
            self._init(kwargs["parent"], kwargs["storage"], kwargs["data"])

        else:
            self._init(None, "json", None)

            if _mode == "any":
                self.set(*args, **kwargs)

            elif _mode == "empty":
                pass

            elif _mode == "fromjson":
                self.set(*args, prop_setter=_prop_setter_json, **kwargs)

            else:
                raise NotImplementedError

    def _init(self, parent, storage, data):
        if parent is not None:
            self._parent = weakref.ref(parent)

        else:
            self._parent = lambda: None

        self._storage = storage
        if storage == "json":
            if data is None:
                data = {}

        else:
            assert data is not None

        self._children = {}
        for prop_name, prop in self._props.items():
            if prop["elementary"]:
                continue

            typename = prop["typename"]
            type_cls = _typenames[typename]

            if self._storage == "json":
                if prop_name not in data:
                    data[prop_name] = {}

            elif self._storage == "numpy":
                pass

            else:
                raise ValueError(self._storage)

            self._children[prop_name] = type_cls(_mode="parent", storage=self._storage, parent=self,
                                                 data=data[prop_name])
        self._data = data

    @classmethod
    def fromjson(cls, data):
        return cls(data, _mode="fromjson")

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
                    elif isinstance(a, list) or isinstance(a, tuple):
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
        self._validate()

    def _validate(self):
        pass

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

    def make_numpy(self, data=None):
        if self._storage == "numpy":
            if data is not None:
                self._data[:] = data

            return

        old_data = self.json()
        data = np.zeros(dtype=self._dtype, shape=(1,))
        self._init(self._parent(), "numpy", data[0])
        self._storage_enum = self._storage_names.index("numpy")

        for prop, value in old_data.items():
            self._set_prop(prop, value, _prop_setter_json)

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
        raise NotImplementedError

    _storage_names = ("numpy", "json", "mixed")

    @property
    def _storage(self):
        return self._storage_names[self._storage_enum]

    @_storage.setter
    def _storage(self, storage):
        assert storage in self._storage_names, storage
        self._storage_enum = self._storage_names.index(storage)

    def __dir__(self):
        return list(self._props)

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            object.__setattr__(self, attr, value)

        else:
            self._set_prop(attr, value, _prop_setter_any)

    def _set_prop(self, prop, value, child_prop_setter):
        try:
            is_elementary = self._props[prop]["elementary"]

        except KeyError:
            raise AttributeError(prop)

        if is_elementary:
            if self._storage == "numpy":
                if value is None and self._has_optional:
                    value = np.ma.masked

            else:
                typename = self._props[prop]["typename"]
                data_type = _typenames[typename]
                value = data_type(value)

            self._data[prop] = value

        else:
            child_prop_setter(self._children[prop], value)

    def __getattr__(self, attr):
        try:
            is_elementary = self._props[attr]["elementary"]

        except KeyError:
            raise AttributeError(attr)

        if is_elementary:
            value = self._data[attr]

        else:
            value = self._children[attr]

        if value is np.ma.masked:
            return None

        else:
            return value

    # TODO cleanup
    def _print(self, spaces):
        as_str = "{0} (\n".format(self.__class__.__name__)

        for prop_name in self._props:
            prop = self._props[prop_name]
            value = getattr(self, prop_name)
            if prop["optional"]:
                if value is None:
                    continue

            if self._storage == "numpy" and prop["elementary"]:
                if value.dtype == '|S10':
                    sub_string = '"' + value.decode() + '"'

                else:
                    sub_string = str(value)
            else:
                sub_string = value._print(spaces+2)

            as_str += "{0}{1} = {2},\n".format(" " * (spaces+2), prop_name, sub_string)

        as_str += "{0})".format(" " * spaces)
        return as_str

    def __str__(self):
        return self._print(0)

    def __repr__(self):
        return self._print(0)
