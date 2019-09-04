import jsonschema
import inspect
import sys
import numpy as np
#from collections.abc import MutableSequence, MutableMapping
from jsonschema.exceptions import FormatError, ValidationError
_types = {
    u"array": list,
    u"boolean": bool,
    u"null": type(None),
    u"object": dict,
}
_integer_types =  (int, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64)
_unsigned_types = (np.uint8, np.uint16, np.uint32, np.uint64)
_float_types = (float, np.float16, np.float32, np.float64, np.float128)
_array_types = (list, tuple, np.ndarray) #don't add MutableSequence for now..,
_string_types = (str, bytes)
_types["array"] = _array_types
_types["integer"] = _integer_types
_types["number"] = _integer_types + _float_types
_types["string"] = _string_types
#_types["object"] = (dict, MutableMapping) #don't do, for now..

Scalar = (type(None), bool, str, bytes) + _integer_types + _float_types
_allowed_types = Scalar + _array_types + (np.void, dict)

def is_np_struct(data):
    return isinstance(data, np.void) and not data.dtype.isbuiltin and len(data.dtype.fields)

def infer_type(value):
    if isinstance(value, dict):
        type_ = "object"
    elif isinstance(value, _array_types):
        type_ = "array"
    elif isinstance(value, bool):
        type_ = "boolean"
    elif isinstance(value, _integer_types):
        type_ = "integer"
    elif isinstance(value, _float_types):
        type_ = "number"
    elif isinstance(value, _string_types):
        type_ = "string"
    elif value is None:
        type_ = "null"
    elif is_np_struct(value):
        type_ = "object"
    else:
        raise TypeError(type(value))
    return type_

def scalar_conv(value):
    if value is None:
        return None
    if isinstance(value, (bool, str, int, float)):
        return value
    if isinstance(value, _integer_types):
        return int(value)
    if isinstance(value, _float_types):
        return float(value)
    if isinstance(value, bytes):
        return value.decode()
    raise TypeError(value)

semantic_keywords = set(("enum", "const", "multipleOf", "minimum", "maximum",
 "exclusiveMinimum", "exclusiveMaximum", "maxLength", "minLength", "pattern"))

def is_numpy_structure_schema(schema):
    """Returns is the schema is a Numpy structure schema
    For such a schema, no elements (items) need to be validated
    This massively speeds up schema validation for large Numpy arrays"""
    if "storage" not in schema:
        return False
    if schema["storage"] not in ("binary", "pure-binary"):
        return False
    if "form" not in schema:
        return False
    if "ndim" not in schema["form"]:
        return False
    if "items" not in schema:
        return True
    items_schema = schema["items"]
    if isinstance(items_schema, list):
        return False
    if "validators" in items_schema:
        return False
    if set(items_schema.keys()).intersection(semantic_keywords):
        return False
    return True

from .formwrapper import FormWrapper
from .validators import (
    validator_items, validator_storage, 
    validator_form, validator_validators
)
from jsonschema import TypeChecker
def typecheck(checker, instance, types):
    return isinstance(instance, types)

import functools    
type_checker = TypeChecker(
    {k: functools.partial(typecheck,types=v) for k,v in _types.items()}
)
schema_validator0 = jsonschema.validators.extend(jsonschema.Draft4Validator, {
    "items": validator_items,
    "form": validator_form,
    "storage": validator_storage,
    "validators": validator_validators
    },
    type_checker=type_checker
)
class schema_validator(schema_validator0):
    def is_type(self, instance, type):
        if isinstance(instance, FormWrapper):
            instance = instance._wrapped
        if type == "object" and is_np_struct(instance):
            return True
        return super().is_type(instance, type)

