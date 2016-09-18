import numpy as np
from collections import OrderedDict
import weakref

# .dict() returns SilkOrderedDict: ordered but prints as normal dict
#   derivative class of OrderedDict

#todo:
# - composite exception for constructor
# - validationblock, errorblock, methodblock
# - init (as string, to be eval'ed)

from ..registers.typenames import _typenames
from . import SilkObject

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

    def set(self, *args, **kwargs):
        try:
            self._construct(*args, **kwargs)
        except:
            if len(args) == 1 and len(kwargs) == 0:
                try:
                    a = args[0]
                    if isinstance(a, dict):
                        self._construct(**a)
                    elif isinstance(a, str):
                        self._parse(a)
                    elif isinstance(a, list) or isinstance(a, tuple):
                        self._construct(*a)
                    elif isinstance(a, SilkObject):
                        d = {prop:getattr(a, prop) for prop in dir(a)}
                        self._construct(**d)
                    else:
                        self._construct(**a.__dict__)
                except:
                    raise
            else:
                raise

    def dict(self):
        d = OrderedDict()
        empty = True
        for attr in self._props:
            ele = self._props[attr]["elementary"]
            if ele:
                ret = self._data[attr]
                if ret is np.ma.masked:
                    ret = None
            else:
                ret = self._children[attr].dict()
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
        old_data = self.dict()
        data = np.zeros(dtype=self._dtype,shape=(1,))
        self._init(self._parent(), "numpy", data[0])
        self._storage_enum = self._storage_names.index("numpy")
        for prop, value in old_data.items():
            self._set_prop(prop, value)

    def _construct(self, *args, **kwargs):
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
                message = "{0}() got multiple values for argument '{1}'".format(
                  self.__class__.__name__,
                  argname
                )
                raise TypeError(message)
            propdict[argname] = a
        missing = [p for p in self._props if p not in propdict]
        missing_required = [p for p in missing
                            if not self._props[p]["optional"]]
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
            self._set_prop(propname, value)

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
            self._set_prop(attr, value)

    def _set_prop(self, prop, value):
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
            self._children[prop].set(value)

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
