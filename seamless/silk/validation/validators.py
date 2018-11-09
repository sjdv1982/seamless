"""
Custom validators that extend or overrule the standard JSON schema validators
"""
from ...mixed.get_form import get_form
from jsonschema.exceptions import FormatError, ValidationError
from jsonschema._validators import items as validator_items_ORIGINAL
from jsonschema._validators import type_draft4 as validator_type_ORIGINAL
import traceback
import numpy as np

from .formwrapper import FormWrapper
from . import is_numpy_structure_schema
from ..SilkBase import compile_function
from .. import _types

"""
TODO: storage is now often re-computed (see TODO:BAD below)
 because FormWrappers are unwrapped when passing into the validators
 of the vanilla jsonschema library.
For now, this seems to be not too costly, so low-priority fix
"""

def validator_items(validator, items, instance, schema):
    """Replacement for the validation of "items"
    Pass-through to the standard validator if any of the following:
    - The data is not a Numpy array
    - The schema is not a Numpy schema, defined as .storage="binary"
       and .form.ndim present.
    - The data is in mixed-binary form
    """
    data = instance
    if isinstance(data, FormWrapper):
        data = data._wrapped
    if isinstance(data, np.ndarray):
        numpy_schema = is_numpy_structure_schema(schema)
        if numpy_schema:
            if isinstance(instance, FormWrapper):
                storage, form = instance._storage, instance._form
            else:
                storage, form = get_form(instance)
            if storage != "mixed-binary":
                return
    return validator_items_ORIGINAL(validator, items, data, schema)

def validator_type(validator, types, instance, schema):
    if isinstance(instance, FormWrapper):
        instance = instance._wrapped
    return validator_type_ORIGINAL(validator, types, instance, schema)


def _validator_storage(storage, instance_storage):
    #TODO: raise proper ValidationErrors
    storages = ("pure-plain", "mixed-plain", "pure-binary", "mixed-binary")
    assert instance_storage in storages, (instance_storage, storages)
    if storage in storages:
        assert storage == instance_storage
    elif storage in ("binary", "plain"):
        assert instance_storage.endswith(storage), (instance_storage, storage)
    else:
        raise ValueError(storage) #schema storage value is not among allowed values

def validator_storage(validator, storage, instance, schema):
    if isinstance(instance, FormWrapper):
        instance_storage = instance._storage
    else:
        #TODO:BAD
        instance_storage, _ = get_form(instance)
    _validator_storage(storage, instance_storage)

def validator_form(validator, form, instance, schema):
    #TODO: nicer ValidationErrors
    """
    - Silk form validators
      - Every "form" property must be either absent or present
      - If present, the form must have exactly that value
      - Or, the "form" property must be a list, and have one of the values in the list
        Or, if numeric, it must have one of the values between any two adjacent ascending list items
      - The above applies a bit differently for shape, as it is already a list:
        - Or, the "form" property must be a list of lists. The property must have the same length.
          For each item in the lists-of-lists, the property must have one of the values, or
          be between any two adjacent ascending list items.
      - Validation on "strides" works through exact match of the strides value.
        Note that "strides" is only present if "contiguous" is absent (and vice versa)
    """
    if isinstance(instance, FormWrapper):
        instance_storage, instance_form = instance._storage, instance._form
    else:
        #TODO:BAD
        instance_storage, instance_form = get_form(instance)
    if "storage" in instance_form:
        _validator_storage(instance_form["storage"], instance_storage)
    for key, value in sorted(form.items(),key=lambda item:item[0]):
        if key not in instance_form:
            raise ValidationError(key)
        instance_value = form[key]
        if key == "strides":
            if value != instance_value:
                raise ValidationError(key, value, instance_value)
        elif key == "shape":
            assert len(value) == len(instance_value) #TODO: check before for inconsistent shape/ndim requirement
            for 
        if isinstance(instance_value, types["number"]):
            if isinstance(value, types["number"]):
                if value !=



def validator_validators(validator, validators, instance, schema):
    if not len(validators):
        return
    from ..Silk import Silk
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

__all__ = ["validator_items", "validator_type", "validator_storage", "validator_form", "validator_validators"]
