import inspect, sys, traceback
from types import MethodType
from copy import copy, deepcopy
import numpy as np

from .SilkBase import SilkBase, SilkHasForm, compile_function
from .validation import (
  schema_validator, FormWrapper,
  Scalar, scalar_conv, _types, infer_type, is_numpy_structure_schema
)
from .schemawrapper import SchemaWrapper

from .policy import default_policy as silk_default_policy
SILK_NO_METHODS = 1
SILK_NO_VALIDATION = 2
SILK_BUFFER_CHILD = 4
SILK_NO_INFERENCE = 8

_underscore_attribute_names =  set(["__array_struct__", "__array_interface__", "__array__"])
# A set of magic names where it is expected that they raise NotImplementedError if
# not implemented, rather than returning NotImplemented
_underscore_attribute_names2 =  set(["__deepcopy__"])
# A set of magic names where it is expected that they raise AttributeError
# not implemented, rather than returning NotImplemented

"""
Buffering:
  Buffered structures have all of their modification written into the buffer, instead of into the data.
  Whenever the buffer is successfully validated (i.e. upon every non-fork modification, or when the fork is joined)
  the buffer is copied into the data. For buffered structures, creating a fork forks the buffer, not the data.
  All data accesses also access the buffer, not the data. To access the data directly, you need to wrap it
  in an unbuffered Silk structure.
"""

#TODO: .self property that becomes a SilkWrapper?
#TODO: .data => _data + data property + ( .self._data in structured_cell)

def _prepare_for_validation(data):
    has_form = False
    if isinstance(data, SilkHasForm):
        storage, form = data._get_silk_form()
        has_form = True
    if isinstance(data, MixedBase):
        # This is hackish, to special-case MixedBase thus
        # But there is really no alternative, except to add
        #  MutableXXX bases classes to ./validation.py
        #  and even then, MixedObject is polymorphic:
        #   it can be dict/list/scalar/None
        # Better to validate the underlying value
        #  (wrapped by MixedBase) instead
        data = data.value
    if isinstance(data, Silk):
        data = data.data
    wdata = data
    if has_form:
        data = FormWrapper(data, form, storage)
    return data, wdata

def init_object_schema(silk, schema):
    if "type" in schema:
        assert schema["type"] == "object"
        if "properties" not in schema:
            schema["properties"] = {}
        return schema["properties"]
    schema["type"] = "object"
    result = {}
    schema["properties"] = result
    if silk._schema_update_hook is not None:
        silk._schema_update_hook()
    return result

class Silk(SilkBase):
    __slots__ = [
            "_parent", "_parent_attr", "data", "_schema",
            "_modifier", "_forks", "_buffer",  "_buffer_nosync",
            "_schema_update_hook", "_schema_dummy"
    ]

    def __init__(self, schema = None, *, parent = None, data = None,
      modifier = 0, buffer = None, schema_update_hook = None,
      _parent_attr = None, schema_dummy = False):
        self._parent = parent
        self._parent_attr = _parent_attr
        self._modifier = modifier
        self._forks = []
        self.data = data
        self._buffer = buffer
        self._buffer_nosync = False
        self._schema_dummy = schema_dummy
        assert not isinstance(data, Silk)
        if schema is None:
            schema = {}
        elif isinstance(schema, Wrapper):
            assert schema_update_hook is None
            schema_update_hook = schema._exported_update_hook
            schema = schema._unwrap()
        assert isinstance(schema, dict) #  Silk provides its own smart wrapper around schema
                                        #   for now, no other wrappers are allowed
                                        #   as this complicates forking and external updates to schema.
                                        #   see the note in structured_cell:"schema could become not a slave"
                                        #   But: a schema update hook is supported
        self._schema = schema
        self._schema_update_hook = schema_update_hook


    def __call__(self, *args, **kwargs):
        data = self.data
        schema = self._schema
        methods = schema.get("methods", {})
        if data is None:
            constructor_code = methods.get("__init__", None)
            if constructor_code is None:
                raise AttributeError("__init__")
            name = "Silk __init__"
            constructor = compile_function(constructor_code, name)
            instance = Silk(data=None,schema=self._schema)
            result = constructor(instance, *args, **kwargs)
            assert result is None # __init__ must return None
            return instance
        else:
            call_code = methods.get("__call__", None)
            if call_code is None:
                raise AttributeError("__call__")
            name = "Silk __call__"
            call = compile_function(call_code, name)
            return call(self, *args, **kwargs)

    @property
    def parent(self):
        if self._parent is None:
            return AttributeError
        return self._parent

    def _get_policy(self, schema, default_policy=None):
        policy = schema.get("policy")
        if policy is None or not len(policy):
            #TODO: implement lookup hierarchy wrapper that also looks at parent
            if default_policy is None:
                default_policy = silk_default_policy
            policy = default_policy
        elif len(policy.keys()) < len(silk_default_policy.keys()):
            policy0 = policy
            policy = deepcopy(silk_default_policy)
            policy.update(policy0)
        return policy

    #***************************************************
    #*  methods for inference
    #***************************************************

    def _is_binary_array(self):
        schema = self._schema
        storage = None
        if "storage" not in schema:
            return False
        if schema["storage"] not in ("binary", "mixed-binary", "pure-binary"):
            return False
        if "form" not in schema:
            return False
        if "ndim" not in schema["form"]:
            return False
        if "type" not in schema or schema["type"] != "array":
            return False
        return True

    def _is_binary_array_item(self):
        if self._parent is None:
            return False
        if self._parent._is_binary_array():
            return True
        schema = self._schema
        storage = None
        if "storage" in schema:
            storage = schema["storage"]
            if storage in ("plain", "mixed-plain", "pure-plain"):
                return False
        return self._parent._is_binary_array_item()

    def _infer_new_property(self, schema, attr, value, value_schema=None):
        if self._modifier & SILK_NO_INFERENCE:
            return False
        schema_updated = False
        policy = self._get_policy(schema)
        if not policy["infer_new_property"]:
            return False
        schema_updated |= self._infer_type(schema, policy, {})
        if "properties" not in schema:
            schema["properties"] = {}
            schema_updated = True
        if attr not in schema["properties"]:
            if value_schema is None:
                value_schema = {}
            schema["properties"][attr] = deepcopy(value_schema)
            schema_updated = True
        subschema = schema["properties"][attr]
        subpolicy = self._get_policy(subschema, policy)
        dummy = Silk(subschema, parent=self)
        schema_updated |= dummy._infer(subpolicy, value)
        return schema_updated

    def _infer_object(self, schema, policy, value, value_schema=None):
        if self._modifier & SILK_NO_INFERENCE:
            return False
        if not policy["infer_object"]:
            return False
        schema_updated = False
        schema_updated |= self._infer_type(schema, policy, value)
        if "properties" not in schema:
            schema["properties"] = {}
            schema_updated = True
        if isinstance(value, dict):
            items = value.items()
        else: #struct
            items = []
            for field in value.dtype.fields:
                subvalue = value[field]
                items.append((field, subvalue))
        if value_schema is None:
            value_schema = {}
        value_schema_props = value_schema.get("properties", {})
        for attr, subvalue in items:
            if attr not in schema["properties"]:
                sub_value_schema = value_schema_props.get(attr, {})
                schema["properties"][attr] = deepcopy(sub_value_schema)
                schema_updated = True
            subschema = schema["properties"][attr]
            subpolicy = self._get_policy(subschema, policy)
            dummy = Silk(subschema, parent=self)
            schema_updated |= dummy._infer(subpolicy, subvalue)
        return schema_updated

    def _infer_new_item(self, schema, pos, value, value_item_schema=None):
        if self._modifier & SILK_NO_INFERENCE:
            return False
        if self._is_binary_array_item():
            return False
        schema_updated = False
        policy = self._get_policy(schema)
        if not policy["infer_new_item"]:
            return False
        schema_updated |= self._infer_type(schema, policy, {})
        if "items" not in schema:
            if value_item_schema is not None:
                item_schema = deepcopy(value_item_schema)
            else:
                item_schema = {}
                dummy = Silk(item_schema, parent=self)
                dummy._infer(policy, value)
            if policy["infer_array"] == "pluriform" and pos == 0:
                item_schema = [item_schema]
            schema["items"] = item_schema
            schema_updated = True
        else:
            item_schema = schema["items"]
            if isinstance(item_schema, list):
                if value_item_schema is not None:
                    new_item_schema = deepcopy(value_item_schema)
                else:
                    new_item_schema = {}
                    dummy = Silk(new_item_schema,parent=self)
                    dummy._infer(policy, value)
                item_schema.insert(pos, new_item_schema)
                schema_updated = True
            else: #single schema, no inference
                pass
        return schema_updated

    def _infer_array(self, schema, policy, value, value_schema=None):
        if self._modifier & SILK_NO_INFERENCE:
            return False
        schema_updated = False
        schema_updated |= self._infer_type(schema, policy, value)
        wvalue = value
        if isinstance(wvalue, MixedBase): #hackish, but necessary (see _prepare_for_validation)
            wvalue = wvalue.value
            if isinstance(wvalue, Silk):
                wvalue = wvalue.data
        if isinstance(wvalue, (list, tuple)):
            storage = "plain"
        elif isinstance(wvalue, np.ndarray):
            storage = "binary"
        else:
            raise TypeError(wvalue)
        if policy["infer_storage"]:
            schema["storage"] = storage
        if storage == "binary":
            if any((
              policy["infer_array"],
              policy["infer_ndim"],
              policy["infer_shape"],
              policy["infer_strides"]
            )):
                if "form" not in schema:
                    schema["form"] = {}
                    schema_updated = True
                form_schema = schema["form"]
            if policy["infer_ndim"]:
                form_schema["ndim"] = wvalue.ndim
                schema_updated = True
            if policy["infer_strides"]:
                contiguous = is_contiguous(wvalue)
                if contiguous:
                    form_schema["contiguous"] = True
                    form_schema.pop("strides", None)
                else:
                    form_schema.pop("contiguous", None)
                    form_schema["strides"] = wvalue.strides
                schema_updated = True
            if policy["infer_shape"]:
                form_schema["shape"] = wvalue.shape
                schema_updated = True
        if not policy["infer_array"]:
            return schema_updated

        if "items" not in schema:
            value_item_schema = None
            if value_schema is not None:
                value_item_schema = value_schema.get("items")
            if value_item_schema is not None:
                schema["items"] = deepcopy(value_item_schema)
                schema_updated = True
            else:
                bytesize = None
                first_item_type = None
                unsigned = None
                if storage == "binary":
                    #TODO: only if parent does not have ndim...
                    if policy["infer_type"] and wvalue.ndim > 1:
                        first_item_type = infer_type(wvalue.flat[0])
                        if first_item_type == "integer":
                            unsigned = is_unsigned(wvalue.dtype)
                    if policy["infer_array"] and policy["infer_storage"]:
                        bytesize = wvalue.itemsize
                        schema_updated = True
                if len(value):
                    pluriform = False
                    item_schema = {}
                    dummy = Silk(item_schema,parent=self)
                    dummy._infer(policy, value[0])
                    if policy["infer_array"] == "pluriform":
                        pluriform = True
                    elif storage == "binary" and is_numpy_structure_schema(schema):
                        #fastest, if we can skip validation altogether
                        #requires that the schema is a numpy structure schema.
                        pass
                    else:
                        # Not too slow (10**5 per sec).
                        #  Much better than constructing and validating
                        #  an explicit Silk object!
                        validator = schema_validator(item_schema)
                        value, _ = _prepare_for_validation(value)
                        for n in range(1, len(value)):
                            try:
                                validator.validate(value[n])
                            except:
                                pluriform = True
                                break
                    if pluriform:
                        item_schemas = [item_schema]
                        for n in range(1, len(value)):
                            item_schemas.append({})
                            dummy = Silk(item_schemas[n],parent=self)
                            dummy._infer(policy, value[n])
                        if bytesize is not None:
                            for item_schema in item_schemas:
                                if "form" not in item_schema:
                                    item_schema["form"] = {}
                                item_schema["form"]["bytesize"] = bytesize
                        if first_item_type is not None:
                            for item_schema in item_schemas:
                                if "form" not in item_schema:
                                    item_schema["form"] = {}
                                item_schema["form"]["type"] = first_item_type
                                if unsigned is not None:
                                    item_schema["form"]["unsigned"] = unsigned
                        schema["items"] = item_schemas
                    else:
                        if bytesize is not None:
                            if "form" not in item_schema:
                                item_schema["form"] = {}
                            item_schema["form"]["bytesize"] = bytesize
                        if first_item_type is not None:
                            if "form" not in item_schema:
                                item_schema["form"] = {}
                            item_schema["form"]["type"] = first_item_type
                            if unsigned is not None:
                                item_schema["form"]["unsigned"] = unsigned
                        schema["items"] = item_schema
                    schema_updated = True
        return schema_updated

    def _infer_type(self, schema, policy, value):
        if self._modifier & SILK_NO_INFERENCE:
            return False
        schema_updated = False
        if policy["infer_type"]:
            if "type" not in schema:
                type_ = infer_type(value)
                if type_ != "null":
                    schema["type"] = type_
                    schema_updated = True
        return schema_updated

    def _infer(self, policy, value):
        if self._modifier & SILK_NO_INFERENCE:
            return False
        schema = self._schema
        if self._is_binary_array_item():
            if not isinstance(value, np.ndarray):
                return self._infer_type(schema, policy, value)
            else:
                return False
        schema_updated = False
        schema_updated |= self._infer_type(schema, policy, value)
        if "type" in schema:
            if schema["type"] == "object":
                schema_updated |= self._infer_object(schema, policy, value)
            elif schema["type"] == "array":
                schema_updated |= self._infer_array(schema, policy, value)
        return schema_updated

    #***************************************************
    #*  methods for setting
    #***************************************************

    def _set_value_simple(self, value, buffer):
        assert self._parent is None or self._parent_attr is not None
        if self._parent is not None:
            self._parent._setitem(self._parent_attr, value)
        elif buffer:
            if isinstance(self._buffer, Monitor):
                self._buffer.set_path((), value)
                return
            self._buffer = value
            return self._buffer
        else:
            if isinstance(self.data, Monitor):
                self.data.set_path((), value)
                return
            self.data = value
            return self.data

    def _set_value_dict(self, value, buffer):
        assert self._parent is None or self._parent_attr is not None
        if self._parent is not None:
            self._parent._setitem(self._parent_attr, value)
            return self.data
        if buffer:
            buffer = self._buffer is not None
        data = self.data
        if buffer:
            data = self._buffer
        if isinstance(data, Monitor):  ### TODO: kludge
            data = data.get_path()
        raw_data = self._raw_data(buffer=buffer)
        is_none = (raw_data is None)
        if isinstance(data, MixedBase):
            data.set(value)
        elif is_none or not isinstance(raw_data, dict) or not isinstance(value, dict):
            self._set_value_simple(value, buffer=buffer)
        else:
            data.clear()
            data.update(value)
        if buffer:
            return self._buffer
        else:
            return self.data

    def _set(self, value, lowlevel, buffer):
        def _get_schema():
            schema = self._schema
            updated = False
            if (schema is None or schema == {}) and value_schema is not None:
                if schema is None:
                    schema = value_schema
                    self._schema = schema
                else:
                    schema.update(value_schema)
                updated = True
            return schema, updated
        schema_updated = False
        value_schema = None
        if isinstance(value, Silk):
            value_schema = value.schema.dict
            value = value.data

        if not lowlevel:
            schema, up = _get_schema()
            schema_updated |= up
            policy = self._get_policy(schema)
            schema_updated |= self._infer_type(schema, policy, value)

        raw_data = self._raw_data(buffer=buffer)        
        is_none = (raw_data is None)
        if isinstance(value, Scalar):
            self._set_value_simple(value, buffer)
            if not lowlevel:
                if value_schema is not None:
                    schema.update(deepcopy(value_schema))
                    schema_updated = True
        elif isinstance(value, _types["array"]):
            #invalidates all Silk objects constructed from items
            if is_none:
                self._set_value_simple(value, buffer)
                is_empty = True
            else:
                is_empty = (len(raw_data) == 0)
            if buffer:
                buffer = self._buffer
                if isinstance(buffer, Monitor):
                    buffer.set_path((), value)
                else:
                    buffer[:] = value
            else:
                data = self.data
                if isinstance(data, Monitor):
                    data.set_path((), value)
                else:                
                    data[:] = value
            if is_empty and not lowlevel:
                schema_updated |= self._infer_array(schema, policy, value, value_schema)
        elif isinstance(value, (dict, np.generic)):
            #invalidates all Silk objects constructed from items
            if is_none:
                is_empty = True
            else:
                is_empty = (len(raw_data) == 0)
            self._set_value_dict(value, buffer)
            schema, up = _get_schema()
            schema_updated |= up
            policy = self._get_policy(schema)
            if is_empty and not lowlevel:
                schema_updated |= self._infer_object(schema, policy, value, value_schema)
        else:
            raise TypeError(type(value))
        if schema_updated and self._schema_update_hook is not None:
            self._schema_update_hook()

    def set(self, value):
        buffer = (self._buffer is not None)
        self._set(value, lowlevel=False, buffer=buffer)
        if not len(self._forks):
            self.validate()
        return self

    def _setitem(self, attr, value):
        buffer = (self._buffer is not None)
        if buffer:
            data = self._buffer
        else:
            data = self.data
        schema = self._schema
        policy = self._get_policy(schema)
        raw_data = self._raw_data(buffer=True)
        schema_updated = False
        if raw_data is None:
            data = self._set_value_simple({}, buffer)
            schema_updated |= self._infer_type(schema, policy, {})
        elif isinstance(data, Monitor):  ### TODO: kludge
            data = data.get_path()
        data[attr] = value
        value_schema = None
        if isinstance(value, Silk):
            value, value_schema = value.data, value._schema
        if isinstance(attr, int):
            schema_updated |= self._infer_new_item(schema, attr, value, value_schema)
        else:
            schema_updated |= self._infer_new_property(schema, attr, value, value_schema)
        if schema_updated and self._schema_update_hook is not None:
            self._schema_update_hook()

    def __setattr__(self, attr, value):
        if attr in type(self).__slots__:
            return super().__setattr__(attr, value)
        if attr in type(self).__dict__ and not attr.startswith("__"):
            raise AttributeError(attr) #Silk method
        if attr == "schema":
            if isinstance(value, SchemaWrapper):
                value = value._dict
            return super().__setattr__(attr, value)
        if isinstance(value, property):
            return self._set_property(attr, value)
        if not isinstance(value, Silk) and callable(value):
            return self._set_method(attr, value)

        schema = self._schema
        m = schema.get("methods", {}).get(attr, None)
        if not (self._modifier & SILK_NO_METHODS) and m is not None:
            if m.get("property", False):
                setter = m.get("setter", None)
                if setter is not None:
                    mm = {"code": setter, "language": m["language"]}
                    name = "Silk .%s setter" % attr
                    fset = compile_function(mm, name)
                    fset(self, value)
                else:
                    raise TypeError(attr) #read-only property cannot be assigned to
            else:
                raise TypeError(attr) #method cannot be assigned to
        else:
            self._setitem(attr, value)
        if not len(self._forks):
            self.validate()

    def __setitem__(self, item, value):
        self._setitem(item, value)
        if not len(self._forks):
            self.validate()

    def _set_property(self, attribute, prop):
        assert (not attribute.startswith("_")) or attribute.startswith("__"), attribute
        assert isinstance(prop, property)
        m = {"property": True, "language": "python"}
        getter_code = inspect.getsource(prop.fget)
        m["getter"] = getter_code
        mm = {"code": getter_code, "language": "python"}
        name = "Silk .%s getter" % attribute
        compile_function(mm, name, mode="property-getter")
        if prop.fset is not None:
            setter_code = inspect.getsource(prop.fset)
            m["setter"] = setter_code
            mm = {"code": setter_code, "language": "python"}
            name = "Silk .%s setter" % attribute
            compile_function(mm, name)
        # TODO: deleter

        schema = self._schema
        methods = schema.get("methods", None)
        if methods is None:
            methods = {}
            schema["methods"] = methods
        methods[attribute] = m
        if self._schema_update_hook is not None:
            self._schema_update_hook()


    def _set_method(self, attribute, func):
        assert (not attribute.startswith("_")) or attribute.startswith("__"), attribute
        assert callable(func)
        code = inspect.getsource(func)
        m = {"code": code, "language": "python"}
        name = "Silk .%s" % attribute
        compile_function(m, name)

        schema = self._schema
        methods = schema.get("methods", None)
        if methods is None:
            methods = {}
            schema["methods"] = methods
        methods[attribute] = m
        if self._schema_update_hook is not None:
            self._schema_update_hook()

    def _add_validator(self, func, attr, *, from_meta, name):
        assert callable(func)
        code = inspect.getsource(func)

        schema = self._schema
        validators = schema.get("validators", None)
        if validators is None:
            l = 1
        else:
            l = len(validators) + 1
        v = {"code": code, "language": "python"}
        func_name = "Silk validator %d" % l
        if name is not None:
            v["name"] = name
            func_name = name
        compile_function(v, func_name)

        if isinstance(attr, int):
            items_schema = schema.get("items", None)
            if items_schema is None:
                #TODO: check for uniform/pluriform
                items_schema = {}
                schema["items"] = items_schema
            schema = items_schema
        elif isinstance(attr, str):
            prop_schema = schema.get("properties", None)
            if prop_schema is None:
                prop_schema = init_object_schema(self, schema)
            attr_schema = prop_schema.get(attr, None)
            if attr_schema is None:
                attr_schema = {}
                prop_schema[attr] = attr_schema
            schema = attr_schema
        if validators is None:
            validators = []
            schema["validators"] = validators
        if name is not None:
            validators[:] = [v for v in validators if v.get("name") != name]
        validators.append(v)
        if self._schema_update_hook is not None:
            self._schema_update_hook()

    def add_validator(self, func, attr=None, *, name=None):
        schema = self._schema
        old_validators = copy(schema.get("validators", None))
        ok = False
        try:
            self._add_validator(func, attr, from_meta=False,name=name)
            self.validate(full = False)
            ok = True
        finally:
            if not ok:
                schema.pop("validators", None)
                if old_validators is not None:
                    schema["validators"] = old_validators

    #***************************************************
    #*  methods for getting
    #***************************************************

    def _raw_data(self, buffer):
        if buffer and self._buffer is not None:
            data = self._buffer
        else:
            data = self.data
        if isinstance(data, Monitor): #hackish, but necessary
            data = data.get_path()
        if isinstance(data, MixedBase): #hackish, but necessary (see _prepare_for_validation)
            data = data.value
        return data

    def _get_special(self, attr, skip_modify_methods = False):
        if attr in ("validate", "add_validator", "set", "parent", "fork") or \
          (attr.startswith("_") and not attr.startswith("__")):
            return super().__getattribute__(attr)

        if self._buffer is not None:
            self._buffer
            self._schema
            self._modifier
            proxy = Silk(data = self._buffer,
                         schema = self._schema,
                         modifier = self._modifier | SILK_BUFFER_CHILD,
                         parent = self,
                         schema_update_hook = self._schema_update_hook,
                         schema_dummy = self._schema_dummy
                    )
            proxy._forks = self._forks
            return proxy._get_special(attr, skip_modify_methods)

        if not skip_modify_methods:
            is_modifying_method, result = try_modify_methods(self, attr)
            if is_modifying_method:
                return result

        data, schema = self.data, self._schema
        if attr == "self":
            return Silk(data = data,
                        schema = schema,
                        modifier = self._modifier | SILK_NO_METHODS,
                        parent = self._parent,
                        schema_update_hook = self._schema_update_hook,
                        schema_dummy = self._schema_dummy
                   )

        if not self._modifier & SILK_NO_METHODS:
            m = schema.get("methods", {}).get(attr, None)
            if m is not None:
                if m.get("property", False):
                    getter = m.get("getter", None)
                    if getter is not None:
                        mm = {"code": getter, "language": m["language"]}
                        name = "Silk .%s getter" % attr
                        fget = compile_function(mm, name, "property-getter")
                        return fget(self)
                else:
                    name = "Silk .%s" % attr
                    method = compile_function(m, name)
                    return MethodType(method, self)
        if attr in type(self).__slots__:
            return super().__getattribute__(attr)
        data = self.data
        if hasattr(type(data), attr):
            return getattr(data, attr)
        if attr.startswith("__"):
            if attr in _underscore_attribute_names:
                raise NotImplementedError
            elif attr in _underscore_attribute_names2:
                raise AttributeError(attr)
            else:
                return NotImplemented
        raise AttributeError(attr)

    def __getattribute__(self, attr):
        if attr in ("data", "_buffer"):
            return super().__getattribute__(attr)
        if attr == "schema":
            return SchemaWrapper(
                self,
                super().__getattribute__("_schema"),
                super().__getattribute__("_schema_update_hook"),
             )
        try:
            return super().__getattribute__("_get_special")(attr)
        except (TypeError, KeyError, AttributeError, IndexError) as exc:
            if attr.startswith("_"):
                raise AttributeError(attr) from None
            try:
                return deepcopy(self._schema["__prototype__"][attr])
            except KeyError:
                pass
            try:
                return super().__getattribute__("_getitem")(attr)
            except (TypeError, KeyError, AttributeError, IndexError):
                raise AttributeError(attr) from None
            except:
                raise exc from None

    def _getitem(self, item):
        data, schema = self.data, self._schema
        modifier = self._modifier
        if self._buffer is not None:
            data = self._buffer
            modifier = modifier | SILK_BUFFER_CHILD
        if isinstance(item, str) and hasattr(data, item):
            result = getattr(data, item)
            d = result
        else:
            d = data[item]
        if isinstance(d, Scalar):
            return scalar_conv(d)
        if isinstance(item, slice):
            # TODO: slice "items" schema if it is a list
            return Silk(
                parent=self,
                data=d,
                schema=schema,
                modifier=SILK_NO_VALIDATION | modifier,
                _parent_attr=item,
                schema_update_hook = self._schema_update_hook,
                schema_dummy = self._schema_dummy
            )

        if isinstance(item, int):
            schema_items = schema.get("items", None)
            child_schema = None
            if schema_items is None:
                schema_items = {}
                schema["items"] = schema_items
                if self._schema_update_hook is not None:
                    self._schema_update_hook()
            elif isinstance(schema_items, list):
                child_schema = schema_items[item]
        else:
            schema_props = schema.get("properties", None)
            if schema_props is None:
                schema_props = init_object_schema(self, schema)
            child_schema = schema_props.get(item, None)
            if child_schema is None:
                child_schema = {}
                schema_props[item] = child_schema
                if self._schema_update_hook is not None:
                    self._schema_update_hook()
        result = Silk(
          parent=self,
          data=d,
          schema=child_schema,
          modifier=modifier,
          _parent_attr=item,
          schema_update_hook = self._schema_update_hook,
          schema_dummy = self._schema_dummy
        )
        return result

    def __getitem__(self, item):
        if isinstance(item, str):
            try:
                return self._getitem(item)
            except (TypeError, KeyError, AttributeError) as exc:
                try:
                    return self._get_special(item)
                except (TypeError, KeyError, AttributeError) as exc2:
                    raise exc2 from None
                else:
                    raise exc from None
        else:
            return self._getitem(item)



    def _validate(self, full, accept_none):
        if not self._modifier & SILK_NO_VALIDATION:
            if full:
                if self._buffer is not None:
                    data = self._buffer
                else:
                    data = self.data
                if isinstance(data, Monitor): ### TODO: kludge
                    data = data.get_path()                                
                data, wdata = _prepare_for_validation(data)
                if wdata is None and accept_none:
                    return                
                if isinstance(data, MixedBase): #hackish (see _prepare_for_validation)
                    data = data.value
                schema_validator(self._schema).validate(data)
            else:
                schema = self._schema
                proxy = self
                data = self.data
                if isinstance(data, Monitor): ### TODO: kludge
                    data = data.get_path()
                if self._buffer is not None:
                    data = self._buffer
                if self._buffer is not None or isinstance(data, MixedBase):
                    modifier = self._modifier
                    if self._buffer is not None:
                        modifier = modifier | SILK_BUFFER_CHILD
                    if isinstance(data, MixedBase): #hackish (see _prepare_for_validation)
                        data = data.value
                    if isinstance(data, Silk):
                        data = data.data
                    if data is None and accept_none:
                        return
                    proxy = type(self)(
                      schema, parent=self._parent, data=data, modifier=modifier,
                    )
                    proxy._forks = self._forks
                validators = schema.get("validators", [])
                for v, validator_code in enumerate(validators):
                    name = "Silk validator %d" % (v+1)
                    validator_func = compile_function(validator_code, name)
                    validator_func(proxy)
        if self._parent is not None:
            self.parent.validate(full=False, accept_none=accept_none)

    def _commit_buffer(self):        
        buffer = self._buffer
        if isinstance(buffer, Monitor):
            buffer = buffer.get_path().value
        buffer = deepcopy(buffer)
        self._set(buffer,lowlevel=True,buffer=False)
        self._buffer_nosync = False

    def validate(self, full=True, accept_none=False):
        if self._schema_dummy:
            accept_none = True
        if (self._modifier & SILK_BUFFER_CHILD) or self._buffer is not None:
            try:
                self._validate(full=full, accept_none=accept_none)
                if self._buffer is not None:
                    self._commit_buffer()
            except:
                #TODO: store exception instead
                print("Warning: exception in buffered Silk structure")
                traceback.print_exc() ###
                self._buffer_nosync = True
        else:
            self._validate(full=full, accept_none=accept_none)

    def fork(self):
        if self._buffer is not None:
            return _BufferedSilkFork(self)
        else:
            return _SilkFork(self)

class _SilkFork:
    _joined = False
    def __init__(self, parent):
        self.parent = parent
         #for now, no smart wrappers around schema are allowed; see above
        assert isinstance(parent._schema, dict), type(parent._schema)
        self.data = deepcopy(parent.data)
        self._schema = deepcopy(parent._schema)
        parent._forks.append(self)

    def _join(self, exception):
        parent = self.parent
        ok = False
        try:
            if exception is None:
                parent.validate()
                ok = True
        finally:
            if not ok:
                parent._set(self.data, lowlevel=True, buffer=False)
                parent._schema.clear()
                parent._schema.update(self._schema)
                if parent._schema_update_hook is not None:
                    parent._schema_update_hook()
            if len(parent._forks): #could be, because of exception
                parent._forks.pop(-1) #should return self
            self._joined = True

    def join(self):
        self._join(None)

    def __enter__(self):
        yield parent

    def __exit__(self, exc_type, exc_value, traceback):
        self._join(exc_value)

    def __del__(self):
        if self._joined:
            return
        self._join(None)

class _BufferedSilkFork(_SilkFork):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        buffer = parent._buffer
        if not isinstance(buffer, Monitor):
            buffer = deepcopy(buffer)
        self._buffer = buffer

    def _join(self, exception):
        parent = self.parent
        ok = False
        validated = False
        try:
            if exception is None:
                b = parent._buffer
                try:
                    parent._buffer = None
                    parent.validate() #should not affect
                    validated = True
                finally:
                    parent._buffer = b
                parent._commit_buffer()
                ok = True
        finally:
            if not ok:
                if exception is None:
                    if validated: #_commit_buffer went wrong, data may be corrupted
                        parent._set(self.data, lowlevel=True, buffer=False)
                    parent._set(self._buffer, lowlevel=True, buffer=True)
                parent._schema.clear()
                parent._schema.update(self._schema)
                if parent._schema_update_hook is not None:
                    parent._schema_update_hook()
            if len(parent._forks): #could be, because of exception
                parent._forks.pop(-1) #should return self
            self._joined = True

from .modify_methods import try_modify_methods
from ..mixed import MixedBase, is_contiguous, is_unsigned
from .. import Wrapper
from ..mixed.Monitor import Monitor