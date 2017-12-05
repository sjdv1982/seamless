import jsonschema
import inspect
import sys
import numpy as np
from jsonschema.exceptions import FormatError, ValidationError
_types = jsonschema.Draft4Validator.DEFAULT_TYPES.copy()
_integer_types =  (int, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64)
_float_types = (float, np.float16, np.float32, np.float64, np.float128)
_types["array"] = (list, tuple, np.ndarray)
_types["integer"] = _integer_types
_types["number"] = _integer_types + _float_types

Scalar = (type(None), bool, str, bytes) + _integer_types + _float_types
import traceback

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

"""
def validator_storage(validator, storage, instance, schema):
    if "form" in storage:
        if not validator.is_type(instance, "object") and not validator.is_type(instance, "array"):
            return
        # TODO: get the internal Silk form descriptor for effiency
        if not isinstance(instance, np.ndarray):
            yield ValidationError("Should be numpy")
"""
def validator_validators(validator, validators, instance, schema):
    if not len(validators):
        return
    from .Silk import Silk
    silkobject = Silk(data=instance, schema=schema) #containing the methods
    for validator_code in validators:
        validator_func = compile_function(validator_code)
        try:
            validator_func(silkobject)
        except Exception:
            msg = traceback.format_exc()
            yield ValidationError("\n"+msg)

validator0 = type("validator", (jsonschema.Draft4Validator,), {"DEFAULT_TYPES": _types})
schema_validator = jsonschema.validators.extend(validator0, {
    #"object": validator_object
    #"items": validator_items
    #"storage": validator_storage,
    "validators": validator_validators
})
