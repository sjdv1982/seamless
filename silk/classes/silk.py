import numpy as np
from collections import OrderedDict
import weakref

# TODO
# - .json() returns SilkOrderedDict: ordered but prints as normal dict
#   derivative class of OrderedDict
# - composite exception for constructor

from ..registers.typenames import _typenames
from . import SilkObject


def _prop_setter_any(child, value): return child.set(value)


def _prop_setter_json(child, value):
    return child.set(value, prop_setter=_prop_setter_json)


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
            self._init(
                kwargs["parent"],
                kwargs["storage"],
                kwargs["data"],
            )
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
        for pname, p in self._props.items():
            if p["elementary"]:
                continue
            typename = p["typename"]
            t = _typenames[typename]
            if self._storage == "json":
                if pname not in data:
                    data[pname] = {}
            elif self._storage == "numpy":
                pass
            else:
                raise ValueError(self._storage)
            self._children[pname] = t(
              _mode="parent",
              storage=self._storage,
              parent=self,
              data=data[pname]
            )
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
        d = OrderedDict()
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
        propdict = {}
        if len(args) > len(self._positional_args):
            message = "{0}() takes {1} positional arguments \
            but {2} were given".format(
              self.__class__.__name__,
              len(self._positional_args),
              len(args)
            )
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
                    ", and" + missing_required[-1]
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
            ele = self._props[prop]["elementary"]
        except KeyError:
            raise AttributeError(prop)
        if ele:
            if self._storage == "numpy":
                if value is None \
                  and self._has_optional:
                    value = np.ma.masked
            else:
                typename = \
                  self._props[prop]["typename"]
                t = _typenames[typename]
                value = t(value)
            self._data[prop] = value
        else:
            child_prop_setter(self._children[prop], value)

    def __getattr__(self, attr):
        try:
            ele = self._props[attr]["elementary"]
        except KeyError:
            raise AttributeError(attr)
        if ele:
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
            if self._storage == "numpy" and prop["elementary"]:
                if value.dtype == '|S10':
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
