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

MAGIC_NUMPY = b"\x93NUMPY"
MAGIC_SEAMLESS = b'\x93SEAMLESS'
MAGIC_SEAMLESS_MIXED = b'\x94SEAMLESS-MIXED'

import numpy as np
from functools import partialmethod

from ..silk.SilkBase import binary_special_method_names
from .. import Wrapper
from ..silk.validation import (
  _array_types, _integer_types, _float_types, _string_types, _unsigned_types,
  _allowed_types, Scalar, is_np_struct, FormWrapper
)

scalars = ("boolean", "integer", "number", "string")

import numpy as np

def is_numpy_buffer(buffer):
    if buffer is None:
        return False
    return buffer[:len(MAGIC_NUMPY)] == MAGIC_NUMPY

class MonitorTypeError(TypeError):
    pass

class MixedBase(Wrapper):
    def __init__(self, _monitor, _path):
        self._monitor = _monitor
        self._path = _path
    def _unwrap(self):
        return FormWrapper(self.value, self.form, self.storage)
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
    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return super().__setattr__(attr, value)
        return self.__setitem__(attr, value)
        raise AttributeError(attr)
    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        if isinstance(self.value, np.ndarray):
            return getattr(self.value, attr)
        else:
            return self.__getitem__(attr)
        raise AttributeError(attr)
    def __str__(self):
        return str(self.value)
    def __repr__(self):
        return repr(self.value)

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
    def __getitem__(self, item):
        value = self.value
        if not isinstance(value, (str, np.ndarray)):
            raise TypeError(type(value))
        return value[item]

for name in binary_special_method_names:
    if name.startswith("__i"):
        name2 = "__" + name[3:]
        m = partialmethod(mixed_scalar_binary_method_inplace, name2=name2)
    else:
        m = partialmethod(mixed_scalar_binary_method, name=name)
    setattr(MixedScalar, name, m)


from .MixedDict import MixedDict
from .MixedObject import MixedObject
from .Monitor import Monitor
from .Backend import Backend, DefaultBackend, SilkBackend
from .get_form import is_contiguous, is_unsigned
