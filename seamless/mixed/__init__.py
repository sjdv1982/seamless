from ..silk.SilkBase import SilkHasForm
from ..silk.validation import _integer_types, _float_types, _string_types, Scalar

class MixedBase(SilkHasForm):
    def _get_silk_form(self):
        return self._form

def get_form_scalar(scalar):
    if isinstance(value, _integer_types):
        type_ = "integer"
    elif isinstance(value, _float_types):
        type_ = "number"
    elif isinstance(value, _string_types):
        type_ = "string"
    elif isinstance(value, bool):
        type_ = "boolean"
    elif value is None:
        type_ = "null"
    else:
        raise TypeError(type(value))
    return type_

from .MixedDict import MixedDict
