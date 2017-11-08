import jsonschema
import numpy as np
from jsonschema.exceptions import FormatError, ValidationError
_types = jsonschema.Draft4Validator.DEFAULT_TYPES.copy()
_types["array"] = (list, tuple, np.ndarray)
_types["integer"] = (int, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64)

#from jsonschema._validators import items as validator_items, object as validator_object

def validator_storage(validator, storage, instance, schema):
    print(instance)
    if "form" in storage:
        if not validator.is_type(instance, "object") and not validator.is_type(instance, "array"):
            return
        # TODO: get the internal Silk form descriptor for effiency
        if not isinstance(instance, np.ndarray):
            yield ValidationError("Should be numpy")

validator0 = type("validator", (jsonschema.Draft4Validator,), {"DEFAULT_TYPES": _types})
validator = jsonschema.validators.extend(validator0, {
    #"object": validator_object
    #"items": validator_items
    "storage": validator_storage
})

schema = { "type": "integer" }
schema2 = {"type": "object", "properties": {"bla": schema}}
schema3 = {"type": "array", "items": schema}
validator(schema).validate(1)
validator(schema2).validate({"a": 1})
arr = np.array([1,2,3])
validator(schema3).validate(arr)

schema3["storage"] = {}
schema3["storage"]["form"] = "binary"
validator(schema3).validate(arr)
print("OK")
validator(schema3).validate([1,2,3])
