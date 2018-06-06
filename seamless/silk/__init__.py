from .Silk import Silk

def is_none(obj):
    if obj is None:
        return True
    if not isinstance(obj, Silk):
        return False
    return obj.data is None

from jsonschema.exceptions import FormatError, ValidationError
