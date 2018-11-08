"""
Python types inside Numpy arrays must be containers, strings, or None, not scalars.
Typedefs are either a string or a typedict with a "type" field containing such a string.
Type strings can be JSON schema types or "tuple", in which case "shape" must be defined
An "array" or "tuple" type contains a field "items", and a field "identical". If "identical" is True, then "items" contains only a single type/typedict,
"object" typedef always contain a field "properties"
A NumPy array (or tuple) of Python objects also has a field "item_storage", which can be "pure-plain" or "mixed-plain", depending on the Python type
If "identical" is False, "item_storage" is a list
In a typedict, a child's "storage" is stored by the parent into a child typedict, but only if:
   1) the child is not pure; or 2) the child is binary and the parent is plain (or vice versa)
"""

MAGIC_SEAMLESS = b'\x93SEAMLESS'

import numpy as np
from functools import partialmethod

from ..silk.SilkBase import SilkHasForm, binary_special_method_names

from ..silk.validation import (
  _array_types, _integer_types, _float_types, _string_types, _unsigned_types,
  _allowed_types, Scalar
)

scalars = ("boolean", "integer", "number", "string")

import numpy as np
np_char = np.dtype('S1')

class MonitorTypeError(TypeError):
    pass

def is_np_struct(data):
    return isinstance(data, np.void) and not data.dtype.isbuiltin and len(data.dtype.fields)

class MixedBase(SilkHasForm):
    def __init__(self, _monitor, _path):
        self._monitor = _monitor
        self._path = _path
    @property
    def value(self):
        data = self._monitor.get_data(self._path)
        return data
    @property
    def form(self):
        return self._monitor.get_form(self._path)
    @property
    def storage(self):
        return self._monitor.get_storage(self._path)
    def set(self, value):
        self._monitor.set_path(self._path, value)
    def _get_silk_form(self):
        return self.form
    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return super().__setattr__(attr, value)
        if self._monitor.attribute_access:
            return self.__setitem__(attr, value)
        raise AttributeError(attr)
    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        if self._monitor.attribute_access:
            return self.__getitem__(attr)
        raise AttributeError(attr)
    def __str__(self):
        return str(self.value)
    def __repr__(self):
        return str(self.value)
    def _get_state(self):
        #TODO: more economic => save just the path sub-state
        return self._monitor._monitor_get_state()
    def _set_state(self, state):
        return self._monitor._monitor_set_state(state)

def mixed_scalar_binary_method(self, other, name):
    if isinstance(other, MixedBase):
        other = other.value
    return getattr(self.value,name)(other)

def mixed_scalar_binary_method_inplace(self, other, name2):
    result = getattr(self.value,name2)(other)
    if result is NotImplemented:
        return NotImplemented
    self._monitor.set_path(self._path, result)
    return result

class MixedScalar(MixedBase):
    pass

for name in binary_special_method_names:
    if name.startswith("__i"):
        name2 = "__" + name[3:]
        m = partialmethod(mixed_scalar_binary_method_inplace, name2=name2)
    else:
        m = partialmethod(mixed_scalar_binary_method, name=name)
    setattr(MixedScalar, name, m)


from .MixedDict import MixedDict, mixed_dict
from .MixedObject import MixedObject
from .Monitor import Monitor
from .MakeParentMonitor import MakeParentMonitor
from .OverlayMonitor import OverlayMonitor
from .get_form import is_contiguous
