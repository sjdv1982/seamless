"""
Custom validators that extend or overrule the standard JSON schema validators
"""
from ...mixed.get_form import get_form
from jsonschema.exceptions import FormatError, ValidationError
from jsonschema._validators import items as validator_items_ORIGINAL
try:
    from jsonschema._validators import type as validator_type_ORIGINAL
except ImportError:    
    from jsonschema._validators import type_draft4 as validator_type_ORIGINAL

from jsonschema._utils import indent
from .formwrapper import FormWrapper
from . import is_numpy_structure_schema, _types
from ..SilkBase import compile_function

import traceback
from bisect import bisect_left
import numpy as np
import pprint
import textwrap
"""
TODO: storage is now often re-computed (see "TODO:BAD" below)
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
    for error in validator_items_ORIGINAL(validator, items, instance, schema):
        yield error

def _validator_storage(storage, instance_storage, form_str=None):
    #TODO: raise proper ValidationErrors
    storages = ("pure-plain", "mixed-plain", "pure-binary", "mixed-binary")
    assert instance_storage in storages, (instance_storage, storages)
    msg = None
    if storage in storages:
        if storage != instance_storage:
            if form_str is None:
                msg = textwrap.dedent("""

                    Property 'storage' has value %r, not %r
                    """.rstrip()
                ) % (instance_storage, storage)
            else:
                msg = textwrap.dedent("""

                    Property 'storage' has value %r, not %r

                    On form:
                    %s
                    """.rstrip()
                ) % (instance_storage, storage, form_str)
    elif storage in ("binary", "plain"):
        if not instance_storage.endswith(storage):
            if form_str is None:
                msg = textwrap.dedent("""

                    Property 'storage' has value %r, does not end with %r
                    """.rstrip()
                ) % (instance_storage, storage)
            else:
                msg = textwrap.dedent("""

                    Property 'storage' has value %r, does not end with %r

                    On form:
                    %s
                    """.rstrip()
                ) % (instance_storage, storage, form_str)
    else:
        raise ValueError(storage) #schema storage value is not among allowed values; TODO: metaschema
    if msg is not None:
        yield ValidationError(msg)

def validator_storage(validator, storage, instance, schema):
    if isinstance(instance, FormWrapper):
        instance_storage = instance._storage
        if instance._storage is None: #huh? to look into later... TODO
            instance_storage, _ = get_form(instance._wrapped)
    else:
        #TODO:BAD
        instance_storage, _ = get_form(instance)
    for error in _validator_storage(storage, instance_storage):
        yield error

def validator_form(validator, form, instance, schema, _from_items=False):
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
    def _allowed_value(schema_value, instance_value):
        if isinstance(schema_value, (list, tuple)):
            if instance_value in schema_value:
                return True
            for n in range(len(schema_value)-1):
                left, right = schema_value[n:n+2]
                if instance_value > left and instance_value < right:
                    return True
            return False
        else:
            return schema_value == instance_value

    if isinstance(instance, FormWrapper):
        instance_storage, instance_form = instance._storage, instance._form
    else:
        #TODO:BAD
        instance_storage, instance_form = get_form(instance)
    form_str = indent(pprint.pformat(instance_form, width=72))
    if instance_form is not None and "storage" in instance_form:
        storage_form = instance_form["storage"]
        for error in _validator_storage(storage_form, instance_storage, form_str):
            yield error
        if instance_storage is None:
            instance_storage = storage_form.get("form")
    if instance_storage is None:
        return

    if _from_items:
        form_str += "\n(on items)"
    binary_form_props = ("unsigned", "shape", "bytesize", "strides", "ndim")
    for key, value in sorted(form.items(),key=lambda item:item[0]):
        if key in binary_form_props and not instance_storage.endswith("binary"):
            continue
        missing_key = None
        if key == "ndim":
            if "shape" not in instance_form:
                missing_key = "'shape' (needed by ndim)"
        else:
            if key not in instance_form:
                missing_key = "'" + key  + "'"
        if missing_key:
            msg = textwrap.dedent("""

                No form property '%s'

                On form:
                %s
                """.rstrip()
            ) % (missing_key, form_str)
            yield ValidationError(msg)
        if key != "ndim":
            instance_value = instance_form[key]
        ok = True
        if key == "ndim":
            instance_value = len(instance_form["shape"])
            if instance_value != value:
                ok = False
        elif key == "strides":
            if value != instance_value:
                ok = False
        elif key == "shape":
            assert len(value) == len(instance_value) #TODO: check before for inconsistent shape/ndim requirement
            for schema_dim, instance_dim in zip(value, instance_value):
                if schema_dim == -1:
                    continue
                if not _allowed_value(schema_dim, instance_dim):
                    ok = False
        elif isinstance(instance_value, _types["number"]):
            if isinstance(value, _types["number"]):
                if not _allowed_value(value, instance_value):
                    ok = False
        else:
            if value != instance_value:
                ok = False
        if not ok:
            msg = textwrap.dedent("""

                Form property '%s' has value %r, not %r

                On form:
                %s
                """.rstrip()
            ) % (key, instance_value, value, form_str)
            yield ValidationError(msg)

    if not _from_items and is_numpy_structure_schema(schema):
        assert instance_storage is not None, schema
        if "items" not in instance_form:
            msg = textwrap.dedent("""

                No form property 'items'

                On form:
                %s
                """.rstrip()
            ) % (form_str,)
            yield ValidationError(msg)
            return
        form_wrapper =  FormWrapper(None, instance_form["items"], instance_storage)
        items_form = schema.get("items", {}).get("form" ,  {})
        for error in validator_form(
            validator,
            items_form, form_wrapper,
            schema, _from_items=True
          ):
            yield error

def validator_validators(validator, validators, instance, schema):
    if not len(validators):
        return
    from ..Silk import Silk, FormWrapper
    if isinstance(instance, FormWrapper):
        instance = instance._wrapped
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
            stars = "*" * 72 + "\n"
            msg2 = "\n" + stars + "*  Silk validation error\n" + stars + msg + stars
            yield ValidationError(msg2)

__all__ = ["validator_items", "validator_storage", "validator_form", "validator_validators"]
