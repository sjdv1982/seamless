import inspect, sys
from types import MethodType
from copy import copy, deepcopy

from .SilkBase import SilkBase, compile_function, AlphabeticDict
from .validation import schema_validator, Scalar, scalar_conv, _types, infer_type
from .schemawrapper import SchemaWrapper

from .policy import default_policy
SILK_NO_METHODS = 1
SILK_NO_VALIDATION = 2


_underscore_attribute_names =  set(["__array_struct__", "__array_interface__", "__array__"])
# A set of magic names where it is expected that they raise NotImplementedError if
# not implemented, rather than returning NotImplemented

class Silk(SilkBase):
    __slots__ = [
            "_parent", "data", "_schema",
            "_modifier", "_forks"
    ]
    # TODO: append method that may also create a schema, depending on policy.infer_item

    def __init__(self, schema = None, *, parent = None, data = None,
      modifier = 0):
        self._parent = parent
        self._modifier = modifier
        self._forks = None
        self.data = data
        assert not isinstance(data, Silk)
        if schema is None:
            schema = {}
        assert isinstance(schema, dict)
        self._schema = schema

    def __call__(self, *args, **kwargs):
        data = self.data
        schema = self._schema
        methods = schema.get("methods", {})
        if data is None:
            constructor_code = methods.get("__init__", None)
            if constructor_code is None:
                raise AttributeError("__init__")
            constructor = compile_function(constructor_code)
            result = constructor(self, *args, **kwargs)
            assert result is None # __init__ must return None
            return self
        else:
            call_code = methods.get("__call__", None)
            if call_code is None:
                raise AttributeError("__call__")
            call = compile_function(call_code)
            return call(self, *args, **kwargs)

    @property
    def parent(self):
        if self._parent is None:
            return AttributeError
        return self._parent.get()

    def set(self, value):
        value_schema = None
        if isinstance(value, Silk):
            value_schema = value.schema.dict
            value = value.data
        if self.data is None:
            self.data = value
            schema = self._schema
            if (schema is None or schema == {}) and value_schema is not None:
                if schema is None:
                    schema = value_schema
                    self._schema = schema
                else:
                    schema.update(value_schema)
            policy = schema.get("policy", None)
            if policy is None or not len(policy):
                #TODO: implement lookup hierarchy wrapper that also looks at parent
                policy = default_policy
            if policy["infer_type"]:
                if "type" not in schema:
                    type_ = infer_type(value)
                    schema["type"] = type_
            if isinstance(value, _types["array"]) and len(self.data) > 0:
                self._infer_list_item(value_schema)
        elif isinstance(value, Scalar):
            assert self._parent is None #MUST be independent
            self.data = value
        elif isinstance(value, _types["array"]):
            #invalidates all Silk objects constructed from items
            empty_list == (len(self.data) == 0)
            self.data[:] = value
            if empty_list:
                self._infer_list_item(value_schema)
        elif isinstance(value, dict):
            #invalidates all Silk objects constructed from items
            old_data = self.data.copy()
            if not isinstance(self.data, dict):
                raise TypeError #  better be strict for now
            self.data.clear()
            self.data.update(value)
        if self._forks is None or self._forks[-1].validate:
            self.validate()
        return self

    def _get(self, attr, skip_modify_methods = False):
        if attr in ("validate", "add_validator", "set", "parent", "fork") or \
          (attr.startswith("_") and not attr.startswith("__")):
            return super().__getattribute__(attr)

        if not skip_modify_methods:
            is_modifying_method, result = try_modify_methods(self, attr)
            if is_modifying_method:
                return result

        data, schema = self.data, self._schema
        if attr == "self":
            return Silk(data = data,
                        schema = schema,
                        modifier = SILK_NO_METHODS)

        if not self._modifier & SILK_NO_METHODS:
            m = schema.get("methods", {}).get(attr, None)
            if m is not None:
                if m.get("property", False):
                    getter = m.get("getter", None)
                    if getter is not None:
                        mm = {"code": getter, "language": m["language"]}
                        fget = compile_function(mm, "property-getter")
                        return fget(self)
                else:
                    method = compile_function(m)
                    return MethodType(method, self)
        if attr in type(self).__slots__:
            return super().__getattribute__(attr)
        data = self.data
        if hasattr(type(data), attr):
            return getattr(data, attr)
        if attr.startswith("__"):
            if attr in _underscore_attribute_names:
                raise NotImplementedError
            else:
                return NotImplemented
        raise AttributeError(attr)

    def __getattribute__(self, attr):
        if attr == "data":
            return super().__getattribute__("data")
        if attr == "schema":
            return SchemaWrapper(super().__getattribute__("_schema"))
        try:
            return super().__getattribute__("_get")(attr)
        except (TypeError, KeyError, AttributeError, IndexError) as exc:
            try:
                return super().__getattribute__("_access_data")(attr)
            except (TypeError, KeyError, AttributeError, IndexError):
                raise AttributeError from None
            except:
                raise exc from None

    def __setattr__(self, attr, value):
        if attr in type(self).__slots__:
            return super().__setattr__(attr, value)
        if attr == "schema":
            if isinstance(value, SchemaWrapper):
                value = value.dict
            return super().__setattr__(attr, value)
        if isinstance(value, property):
            return self._set_property(attr, value)
        if callable(value):
            return self._set_method(attr, value)

        schema = self._schema
        m = schema.get("methods", {}).get(attr, None)
        if not (self._modifier & SILK_NO_METHODS) and m is not None:
            if m.get("property", False):
                setter = m.get("setter", None)
                if setter is not None:
                    mm = {"code": setter, "language": m["language"]}
                    fset = compile_function(mm)
                    fset(self, value)
                else:
                    raise TypeError(attr) #read-only property cannot be assigned to
            else:
                raise TypeError(attr) #method cannot be assigned to
        else:
            data, schema = self.data, self._schema
            policy = schema.get("policy", None)
            if policy is None or not len(policy):
                #TODO: implement lookup hierarchy wrapper that also looks at parent
                policy = default_policy
            if data is None:
                assert self._parent is None # MUST be independent
                data = AlphabeticDict()
                self.data = data
            if isinstance(value, Silk):
                value, value_schema = value.data, value._schema
                if "properties" not in schema:
                    schema["properties"] = {}
                if attr not in schema["properties"]:
                    schema["properties"][attr] = value_schema
                    #TODO: infer_property check
            data[attr] = value

            if policy["infer_type"]:
                if "properties" not in schema:
                    schema["properties"] = {}
                if attr not in schema["properties"]:
                    schema["properties"][attr] = {}
                if "type" not in schema["properties"][attr]:
                    type_ = infer_type(value)
                    schema["properties"][attr]["type"] = type_

            # TODO: make conditional upon policy.infer_property

        if self._forks is None or self._forks[-1].validate:
            self.validate()

    def __setitem__(self, item, value):
        data, schema = self.data, self._schema
        if data is None:
            assert self._parent is None # MUST be independent
            assert isinstance(item, str)
            data = AlphabeticDict()
            self.data = data
        if isinstance(value, Silk):
            value = value.data
        data[item] = value

        if self._forks is None or self._forks[-1].validate:
            self.validate()

    def _infer_list_item(self, item_schema):
        schema = self._schema
        policy = schema.get("policy", None)
        if policy is None or not len(policy):
            #TODO: implement lookup hierarchy wrapper that also looks at parent
            policy = default_policy
        infer_item = policy["infer_item"]
        if infer_item != "uniform":
            raise NotImplementedError(infer_item)
            # TODO: if "pluriform", need a new method:
            #   _infer_additional_list_item must be called for each .append
            #   In addition, deletion/[:] can become quite tricky: ignore?
        assert len(self.data) > 0
        if item_schema is None:
            item = self.data[0]
            s = Silk()
            s.item = item
            item_schema = s.schema.properties.item.dict
        schema["items"] = item_schema

    def _access_data(self, item):
        data, schema = self.data, self._schema
        if isinstance(item, str) and hasattr(data, item):
            return getattr(data, item)
        d = data[item]
        if isinstance(d, Scalar):
            return scalar_conv(d)
        if isinstance(item, slice):
            # TODO: slice "items" schema if it is a list
            return Silk(
                parent= _SilkParent(self),
                data=d,
                schema=schema,
                modifier = SILK_NO_VALIDATION,
            )

        if isinstance(item, int):
            schema_items = schema.get("items", None)
            if schema_items is None:
                schema_items = {}
                schema["items"] = schema_items
            elif isinstance(schema_items, list):
                child_schema = schema_items[item]
        else:
            schema_props = schema.get("properties", None)
            if schema_props is None:
                schema_props = {}
                schema["properties"] = schema_props
            child_schema = schema_props.get(item, None)
            if child_schema is None:
                child_schema = {}
                schema_props[item] = child_schema

        return Silk(
          parent=_SilkParent(self),
          data=d,
          schema=child_schema,
        )

    def __getitem__(self, item):
        if isinstance(item, str):
            try:
                return self._access_data(item)
            except (TypeError, KeyError, AttributeError) as exc:
                try:
                    return self._get(item)
                except (TypeError, KeyError, AttributeError) as exc2:
                    raise exc2 from None
                else:
                    raise exc from None
        else:
            return self._access_data(item)

    def _set_property(self, attribute, prop):
        assert (not attribute.startswith("_")) or attribute.startswith("__"), attribute
        assert isinstance(prop, property)
        m = {"property": True, "language": "python"}
        getter_code = inspect.getsource(prop.fget)
        m["getter"] = getter_code
        mm = {"code": getter_code, "language": "python"}
        compile_function(mm, mode="property-getter")
        if prop.fset is not None:
            setter_code = inspect.getsource(prop.fset)
            m["setter"] = setter_code
            mm = {"code": setter_code, "language": "python"}
            compile_function(mm)
        # TODO: deleter

        schema = self._schema
        methods = schema.get("methods", None)
        if methods is None:
            methods = {}
            schema["methods"] = methods
        methods[attribute] = m

    def _set_method(self, attribute, func):
        assert (not attribute.startswith("_")) or attribute.startswith("__"), attribute
        assert callable(func)
        code = inspect.getsource(func)
        m = {"code": code, "language": "python"}
        compile_function(m)

        schema = self._schema
        methods = schema.get("methods", None)
        if methods is None:
            methods = {}
            schema["methods"] = methods
        methods[attribute] = m

    def _add_validator(self, func, attr, *, from_meta):
        assert callable(func)
        code = inspect.getsource(func)
        v = {"code": code, "language": "python"}
        compile_function(v)

        schema = self._schema
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
                prop_schema = {}
                schema["properties"] = prop_schema
            attr_schema = prop_schema.get(attr, None)
            if attr_schema is None:
                attr_schema = {}
                prop_schema[attr] = attr_schema
            schema = attr_schema
        validators = schema.get("validators", None)
        if validators is None:
            validators = []
            schema["validators"] = validators
        validators.append(v)

    def add_validator(self, func, attr=None):
        schema = self._schema
        old_validators = copy(schema.get("validators", None))
        ok = False
        try:
            self._add_validator(func, attr, from_meta=False)
            self.validate(full = False)
            ok = True
        finally:
            if not ok:
                schema.pop("validators", None)
                if old_validators is not None:
                    schema["validators"] = old_validators

    def validate(self, full = True):
        if not self._modifier & SILK_NO_VALIDATION:
            if full:
                schema_validator(self._schema).validate(self.data)
            else:
                schema = self._schema
                validators = schema.get("validators", [])
                for validator_code in validators:
                    validator_func = compile_function(validator_code)
                    validator_func(self)
        if self._parent is not None:
            self.parent.validate()

    def fork(self):
        return _SilkFork(self)

class _SilkParent:
    """Helper class to provide a path to parent data"""
    def __init__(self, silkobject):
        self.data = silkobject.data
        self._schema = silkobject._schema
    def get(self):
        return Silk(
            data=self.data,
            schema=self._schema,
        )

class _SilkFork:
    validate = False
    _joined = False

    def __init__(self, parent):
        self.parent = parent
        self.data = deepcopy(parent.data)
        self._schema = deepcopy(parent._schema)
        if parent._forks is None:
            parent._forks = []
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
                parent.data = self.data
                parent._schema = self._schema
            parent._forks.pop(-1) #should return self
            if not len(parent._forks):
                parent._forks = None
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

from .modify_methods import try_modify_methods
