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

from ..silk.SilkBase import SilkHasForm
from ..silk.validation import (
  _array_types, _integer_types, _float_types, _string_types, _unsigned_types,
  Scalar
)  

class MixedBase(SilkHasForm):
    def _get_silk_form(self):
        return self._form




from .MixedDict import MixedDict
