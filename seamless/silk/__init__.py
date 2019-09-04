def test_none(obj):
    if obj is None:
        return True    
    if isinstance(obj, Silk):
        data = obj._data
    else:
        data = obj
    if isinstance(data, Wrapper):
        data = data._unwrap()
    return data is None

from .Silk import Silk
from .validation import Scalar
from .. import Wrapper

from jsonschema.exceptions import FormatError, ValidationError
