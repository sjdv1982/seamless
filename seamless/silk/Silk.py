import inspect, sys, traceback
from types import MethodType
from copy import copy, deepcopy
import numpy as np

from .SilkBase import SilkBase, compile_function
from .validation import (
  schema_validator,
  Scalar, scalar_conv, _types, infer_type, is_numpy_structure_schema, ValidationError
)
allowed_types = tuple(_types.values())
from .policy import default_policy as silk_default_policy

_underscore_attribute_names =  set(["__array_struct__", "__array_interface__", "__array__"])
# A set of magic names where it is expected that they raise NotImplementedError if
# not implemented, rather than returning NotImplemented
_underscore_attribute_names2 =  set(["__deepcopy__"])
# A set of magic names where it is expected that they raise AttributeError if
# not implemented, rather than returning NotImplemented

def init_object_schema(silk, schema):
    if "type" in schema:
        assert schema["type"] == "object"
        if "properties" not in schema:
            schema["properties"] = {}
        return schema["properties"]
    schema["type"] = "object"
    result = {}
    schema["properties"] = result
    return result

class RichValue:
    value = None
    form = None
    storage = None
    schema = None
    _has_form = False
    def __init__(self, value, need_form=False):
        if isinstance(value, Wrapper):
            value = value._unwrap()
        if isinstance(value, Silk):
            self.schema = value._schema
            value = value._data
        if isinstance(value, Wrapper):
            value = value._unwrap()
        if isinstance(value, FormWrapper):
            self._form = value._form
            self._storage = value._storage
            value = value._wrapped
            self._has_form = True            
        elif need_form:
            self._storage, self._form = get_form(value)
            self._has_form = True
        self.value = value
    @property
    def form(self):
        assert self._has_form
        return self._form
    @property
    def storage(self):
        assert self._has_form
        return self._storage

def _unwrap_all(value):
    if isinstance(value, Wrapper):
        value = value._unwrap()

class Silk(SilkBase):
    __slots__ = [
            "_data", "_schema", "_parent",
            "_parent_attr",
            "_self_mode"
    ]

    def __init__(self, *,
        data=None, schema=None, 
        parent=None, _parent_attr=None,
        _self_mode=False
    ):
        assert parent is None or isinstance(parent, Silk)
        self._parent = parent
        self._parent_attr = _parent_attr
        assert isinstance(data, allowed_types) \
          or isinstance(data, (Wrapper, FormWrapper))
        self._data = data
        if schema is None:
            schema = {}
        assert isinstance(schema, allowed_types) \
          or isinstance(schema, Wrapper)
        self._schema = schema
        self._self_mode = _self_mode

    def __call__(self, *args, **kwargs):
        data = self._data
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
        policy = self._get_policy(schema)
        if not policy["infer_new_property"]:
            return False
        self._infer_type(schema, policy, {})
        if "properties" not in schema:
            schema["properties"] = {}
        if attr not in schema["properties"]:
            if value_schema is None:
                value_schema = {}
            schema["properties"][attr] = deepcopy(value_schema)
        subschema = schema["properties"][attr]
        subpolicy = self._get_policy(subschema, policy)
        dummy = Silk(schema=subschema, parent=self)
        dummy._infer(subpolicy, RichValue(value))

    def _infer_object(self, schema, policy, rich_value):
        assert isinstance(rich_value, RichValue)
        value = rich_value.value
        value_schema = rich_value.schema
        if not policy["infer_object"]:
            return False
        self._infer_type(schema, policy, value)
        if "properties" not in schema:
            schema["properties"] = {}
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
            subschema = schema["properties"][attr]
            subpolicy = self._get_policy(subschema, policy)
            dummy = Silk(schema=subschema, parent=self)
            dummy._infer(subpolicy, RichValue(subvalue))

    def _infer_new_item(self, schema, index, value, value_item_schema=None):
        if self._is_binary_array_item():
            return False
        policy = self._get_policy(schema)
        if not policy["infer_new_item"]:
            return False
        self._infer_type(schema, policy, {})
        if "items" not in schema:
            if value_item_schema is not None:
                item_schema = deepcopy(value_item_schema)
            else:
                item_schema = {}
                dummy = Silk(schema=item_schema, parent=self)
                dummy._infer(policy, RichValue(value))
            if policy["infer_array"] == "pluriform" and index == 0:
                item_schema = [item_schema]
            schema["items"] = item_schema
        else:
            item_schemas = schema["items"]
            new_item_schema = None
            if isinstance(item_schemas, list):
                if value_item_schema is not None:
                    new_item_schema = deepcopy(value_item_schema)
                else:
                    if index < len(item_schemas):
                        curr_item_schema = item_schemas[index]
                    else:
                        new_item_schema = {}
                        curr_item_schema = new_item_schema
                    dummy = Silk(schema=curr_item_schema,parent=self)
                    dummy._infer(policy, RichValue(value))
                    insert = True
                if new_item_schema is not None:
                    for n in range(len(item_schemas), index):
                        item_schemas.append({})
                    item_schemas.insert(index, new_item_schema)
            else: #single schema, no inference
                pass

    def _infer_array(self, schema, policy, rich_value):
        assert isinstance(rich_value, RichValue)        
        value = rich_value.value
        self._infer_type(schema, policy, value)
        value_schema = rich_value.schema
        if isinstance(value, (list, tuple)):
            storage = "plain"
        elif isinstance(value, np.ndarray):
            storage = "binary"
        else:
            raise TypeError(value)
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
                form_schema = schema["form"]
            if policy["infer_ndim"]:
                form_schema["ndim"] = value.ndim
            if policy["infer_strides"]:
                contiguous = is_contiguous(value)
                if contiguous:
                    form_schema["contiguous"] = True
                    form_schema.pop("strides", None)
                else:
                    form_schema.pop("contiguous", None)
                    form_schema["strides"] = value.strides
            if policy["infer_shape"]:
                form_schema["shape"] = value.shape
        if not policy["infer_array"]:
            return

        if "items" not in schema:
            value_item_schema = None
            if value_schema is not None:
                value_item_schema = value_schema.get("items")
            if value_item_schema is not None:
                schema["items"] = deepcopy(value_item_schema)
            else:
                bytesize = None
                first_item_type = None
                unsigned = None
                if storage == "binary":
                    #TODO: only if parent does not have ndim...
                    if policy["infer_type"] and value.ndim > 1:
                        first_item_type = infer_type(value.flat[0])
                        if first_item_type == "integer":
                            unsigned = is_unsigned(value.dtype)
                    if policy["infer_array"] and policy["infer_storage"]:
                        bytesize = value.itemsize
                if len(value):
                    pluriform = False
                    item_schema = {}
                    dummy = Silk(schema=item_schema,parent=self)
                    dummy._infer(policy, RichValue(value[0]))
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
                        for n in range(1, len(value)):
                            try:
                                validator.validate(value[n])
                            except Exception:
                                pluriform = True
                                break
                    if pluriform:
                        item_schemas = [item_schema]
                        for n in range(1, len(value)):
                            item_schemas.append({})
                            dummy = Silk(schema=item_schemas[n],parent=self)
                            dummy._infer(policy, RichValue(value[n]))
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

    def _infer_type(self, schema, policy, value):
        if policy["infer_type"]:
            if "type" not in schema:
                type_ = infer_type(value)
                if type_ != "null":
                    schema["type"] = type_

    def _infer(self, policy, rich_value):
        assert isinstance(rich_value, RichValue)
        schema = self._schema
        value = rich_value.value
        if self._is_binary_array_item():
            if not isinstance(value, np.ndarray):
                return self._infer_type(schema, policy, value)
            else:
                return False
        self._infer_type(schema, policy, value)
        if "type" in schema:
            if schema["type"] == "object":
                self._infer_object(schema, policy, rich_value)
            elif schema["type"] == "array":
                self._infer_array(schema, policy, rich_value)

    #***************************************************
    #*  methods for setting
    #***************************************************

    def _set_value_simple(self, value):
        assert self._parent is None or self._parent_attr is not None
        if self._parent is not None:
            self._parent._setitem(self._parent_attr, value)
        elif isinstance(self._data, Wrapper):
            self._data.set(value)
        else:
            self._data = value
    
    def _set_value_dict(self, value):
        assert self._parent is None or self._parent_attr is not None
        if self._parent is not None:
            self._parent._setitem(self._parent_attr, value)
            return self._data
        data = self._data
        raw_data = self._raw_data()
        is_none = (raw_data is None)
        if is_none or not isinstance(raw_data, dict) or not isinstance(value, dict):
            self._set_value_simple(value)
        else:
            data.clear()
            data.update(value)
        return self._data

    def _set(self, value, lowlevel):
        rich_value = RichValue(value)
        value = rich_value.value
        value_schema = rich_value.schema
        def _get_schema():
            schema = self._schema
            updated = False
            if test_none(schema) and value_schema is not None:
                if schema is None:
                    schema = value_schema
                    super().__setattr__(self, "_schema", schema)
                else:
                    schema.update(value_schema)
            return schema

        if not lowlevel:
            schema = _get_schema()
            policy = self._get_policy(schema)
            self._infer_type(schema, policy, value)

        raw_data = self._raw_data()        
        is_none = (raw_data is None)
        if isinstance(value, Scalar):
            self._set_value_simple(value)
            if not lowlevel:
                if value_schema is not None:
                    schema.update(deepcopy(value_schema))
        elif isinstance(value, _types["array"]):
            #invalidates all Silk objects constructed from items
            if is_none:
                self._set_value_simple(value)
                is_empty = True
            else:
                is_empty = (len(raw_data) == 0)
            data = self._data
            if isinstance(data, Wrapper):
                data.set(value)
            else:                
                data[:] = value
            if is_empty and not lowlevel:
                self._infer_array(schema, policy, rich_value)
        elif isinstance(value, (dict, np.generic)):
            #invalidates all Silk objects constructed from items
            if is_none:
                is_empty = True
            else:
                is_empty = (len(raw_data) == 0)
            self._set_value_dict(value)
            schema = _get_schema()
            policy = self._get_policy(schema)
            if is_empty and not lowlevel:
                self._infer_object(schema, policy, rich_value)
        else:
            raise TypeError(type(value))
        
    def set(self, value):
        self._set(value, lowlevel=False)
        return self

    def _setitem(self, attr, value, value_schema):        
        data = self._data
        schema = self._schema
        policy = self._get_policy(schema)
        raw_data = self._raw_data()
        if raw_data is None:
            self._set_value_simple({})
            self._infer_type(schema, policy, {})
            data = self._data
        data[attr] = value
        if isinstance(attr, int):
            self._infer_new_item(schema, attr, value, value_schema)
        else:
            self._infer_new_property(schema, attr, value, value_schema)

    def __setattr__(self, attr, value):
        if attr in type(self).__slots__:
            return super().__setattr__(attr, value)
        if hasattr(type(self), attr) and not attr.startswith("__"):
            raise AttributeError(attr) #Silk method
        if attr in ("data", "schema", "unsilk"):
            raise AttributeError
        if isinstance(value, property):
            return self._set_property(attr, value)
        if not isinstance(value, Silk) and callable(value):
            return self._set_method(attr, value)

        rich_value = RichValue(value)
        value, value_schema = rich_value.value, rich_value.schema
        schema = self._schema
        m = schema.get("methods", {}).get(attr, None)
        if m is not None:
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
            self._setitem(attr, value, value_schema)

    def __setitem__(self, item, value):
        rich_value = RichValue(value)
        value, value_schema = rich_value.value, rich_value.schema
        self._setitem(item, value, value_schema)

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

    """
    def _schema_get(self, attribute):
        child = self.schema.get(attribute, None)
        if child is None:
            props = self.schema.get("properties")
            if props is None:
                raise AttributeError(attribute)
            child = props.get(attribute)
            if child is None:
                raise AttributeError(attribute)
        return child
    """

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

    def add_validator(self, func, attr=None, *, name=None):
        assert callable(func)
        code = inspect.getsource(func)

        schema = self.schema

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

    #***************************************************
    #*  methods for getting
    #***************************************************

    def _raw_data(self):
        data = self._data
        return RichValue(data).value

    def _get_special(self, attr, *, skip_modify_methods=False):
        if attr.startswith("_") and not attr.startswith("__"):
            return super().__getattribute__(attr)

        if not skip_modify_methods:
            is_modify_method, result = try_modify_methods(self, attr)
            if is_modify_method:
                return result
        
        data, schema = self._data, self._schema
        if attr == "self":
            return Silk(data = data,
                        schema = schema,
                        _self_mode=True,
                        parent = self._parent,
                        _parent_attr=self._parent_attr
                    
                   )

        if self._self_mode:
            raise AttributeError

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
        data = RichValue(self._data).value
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
        if attr in type(self).__slots__:
            return super().__getattribute__(attr)
        try:
            return super().__getattribute__("_get_special")(attr)
        except (TypeError, KeyError, AttributeError, IndexError) as exc:
            if attr.startswith("_"):
                raise AttributeError(attr) from None
            if hasattr(type(self), attr):                
                return super().__getattribute__(attr)
            if attr in ("data", "schema", "unsilk"):
                if attr == "unsilk":
                    result = getattr(self, "_data")
                else:
                    result = getattr(self, "_" + attr)
                if attr == "data":
                    result = RichValue(result).value
                return result
            if self._self_mode:
                raise exc from None
            proto_ok = False
            try:
                from_proto = deepcopy(self._schema["__prototype__"][attr])
                proto_ok = True
            except KeyError:
                pass
            try:
                return super().__getattribute__("_getitem")(attr)
            except (TypeError, KeyError, AttributeError, IndexError):
                if proto_ok:
                    return Silk(data=from_proto)
                raise AttributeError(attr) from None
            except Exception:
                if proto_ok:
                    return Silk(data=from_proto)
                raise exc from None
    
    def __iter__(self):
        data = RichValue(self._data).value        
        if isinstance(data, (list, tuple, np.ndarray)):
            data_iter = range(len(data)).__iter__()
            return SilkIterator(self, data_iter)
        else:            
            data_iter = data.__iter__()
            return data_iter

    def _getitem(self, item):
        data, schema = self._data, self._schema
        if isinstance(item, str) and hasattr(data, item):
            result = getattr(data, item)
            data2 = data
            if isinstance(data, Wrapper):
                data2 = data._unwrap()
            if isinstance(data2, FormWrapper) and item in ("form", "storage"):
                return result
            d = result
        else:
            d = data[item]
        """
        if isinstance(d, Scalar):
            return scalar_conv(d)
        """
        if isinstance(item, slice):
            # TODO: slice "items" schema if it is a list
            return Silk(
                parent=self,
                data=d,
                schema=schema,
                _parent_attr=item,
            )

        if isinstance(item, int):
            schema_items = schema.get("items", None)
            child_schema = None
            if schema_items is None:
                schema_items = {}
                schema["items"] = schema_items
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
        result = Silk(
          parent=self,
          data=d,
          schema=child_schema,
          _parent_attr=item,
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

    def _get_data_value(self):
        data = self._data
        if isinstance(data, Wrapper):
            data = data._unwrap()
        return data

    def _validate(self):
        need_form = True # TODO: detect "form" in schema, i.e. if validator_form will ever be triggered
        rich_value = RichValue(self._data, need_form)        
        data = FormWrapper(
            rich_value.value,
            rich_value.form,
            rich_value.storage 
        )
        schema = self._schema
        schema_validator(schema).validate(data)

    def validate(self, full=True):
        assert full in (True, False, None), full
        #print("Silk.validate", self, self._parent, full)
        if full != True:
            if full is None:
                self._validate()
            else:
                schema = self._schema
                validators = schema.get("validators", [])
                if len(validators):
                    for v, validator_code in enumerate(validators):
                        name = "Silk validator %d" % (v+1)
                        validator_func = compile_function(validator_code, name)
                        try:
                            validator_func(self)
                        except Exception as exc:
                            tb = traceback.format_exc(limit=3)
                            raise ValidationError("\n"+tb) from None
            if self._parent is not None:
                self._parent.validate(full=False)
        elif self._parent is not None:
            self._parent.validate()
        else:
            self._validate()



class SilkIterator:
    def __init__(self, silk, item_iterator):
        self.silk = silk
        self.item_iterator = item_iterator
    def __next__(self):
        next_item = self.item_iterator.__next__()
        return self.silk[next_item]


from .modify_methods import try_modify_methods
from ..mixed import is_contiguous, is_unsigned
from ..mixed.get_form import get_form
from .validation.formwrapper import FormWrapper
from .. import Wrapper
from . import test_none