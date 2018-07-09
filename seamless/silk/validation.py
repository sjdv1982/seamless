import jsonschema
import inspect
import sys
import numpy as np
#from collections.abc import MutableSequence, MutableMapping
from jsonschema.exceptions import FormatError, ValidationError
_types = jsonschema.Draft4Validator.DEFAULT_TYPES.copy()
_integer_types =  (int, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64)
_unsigned_types = (np.uint8, np.uint16, np.uint32, np.uint64)
_float_types = (float, np.float16, np.float32, np.float64, np.float128)
_array_types = (list, tuple, np.ndarray) #don't add MutableSequence for now..,
_string_types = (str, bytes)
_types["array"] = _array_types
_types["integer"] = _integer_types
_types["number"] = _integer_types + _float_types
#_types["object"] = (dict, MutableMapping) #don't do, for now..

Scalar = (type(None), bool, str, bytes) + _integer_types + _float_types
_allowed_types = Scalar + _array_types + (np.void, dict)

import traceback

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

from .SilkBase import compile_function

def validator_storage(validator, storage, instance, schema):
    raise NotImplementedError

def validator_validators(validator, validators, instance, schema):
    if not len(validators):
        return
    from .Silk import Silk
    if isinstance(instance, Silk):
        instance = instance.self.data
    silkobject = Silk(data=instance, schema=schema) #containing the methods
    for v, validator_code in enumerate(validators):
        name = "Silk validator %d" % (v+1)
        validator_func = compile_function(validator_code, name)
        try:
            validator_func(silkobject)
        except Exception:
            msg = traceback.format_exc()
            yield ValidationError("\n"+msg)

validator0 = type("validator", (jsonschema.Draft4Validator,), {"DEFAULT_TYPES": _types})
schema_validator = jsonschema.validators.extend(validator0, {
    #"object": validator_object
    #"items": validator_items
    "validators": validator_validators
})

form_validator = jsonschema.validators.extend(validator0, {
    "storage": validator_storage,
})
