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

import numpy as np
from ..silk.SilkBase import SilkHasForm
from ..silk.validation import (
  _array_types, _integer_types, _float_types, _string_types, _unsigned_types,
  _allowed_types, Scalar
)

scalars = ("boolean", "integer", "number", "string")


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
        if attr in dir(self):
            return super().__setattr__(attr, value)
        raise AttributeError(attr)


class MixedScalar(MixedBase):
    pass

from .MixedDict import MixedDict, mixed_dict
from .Monitor import Monitor
from .MakeParentMonitor import MakeParentMonitor
from .OverlayMonitor import OverlayMonitor
