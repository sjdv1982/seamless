import weakref
from pprint import pformat
from copy import copy, deepcopy
import inspect

from .. import Wrapper
class SchemaWrapper(Wrapper):
    _update_hook = None
    _parent = lambda self: None
    def __init__(self, _parent, _dict, _update_hook):
        if _parent is not None:
            super().__setattr__("_parent", weakref.ref(_parent))
        if isinstance(_dict, SchemaWrapper):
            _dict = _dict._dict
        super().__setattr__("_dict", _dict)
        if _update_hook is not None:
            super().__setattr__("_update_hook", _update_hook)

    def _unwrap(self):
        return self._dict

    def _get(self, attribute):
        child = self._dict.get(attribute, None)
        if child is None:
            props = self._dict.get("properties")
            if props is None:
                raise AttributeError(attribute)
            child = props.get(attribute)
            if child is None:
                raise AttributeError(attribute)
        return SchemaWrapper(self._parent(), child, self._update_hook)

    def copy(self):
        return SchemaWrapper(None, deepcopy(self._dict), None)

    def update(self, value):        
        if isinstance(value, SchemaWrapper):
            value = value._dict
        self._dict.update(value)
        parent = self._parent()
        if parent is not None:
            parent.validate(accept_none=True)
        if self._update_hook is not None:
            self._update_hook()

    def pop(self, attribute):
        child = self._dict.get(attribute, None)
        if child is None:
            props = self._dict.get("properties", None)
            if props is None:
                raise AttributeError(attribute)
            child = props.get(attribute, None)
            if child is None:
                raise AttributeError(attribute)
            result = props.pop(attribute)
        else:
            result = self._dict.pop(attribute)
        parent = self._parent()
        if parent is not None:
            parent.validate(accept_none=True)
        if self._update_hook is not None:
            self._update_hook()
        return result

    def _add_validator(self, func, attr, *, from_meta, name):
        assert callable(func)
        code = inspect.getsource(func)

        schema = self._dict
        parent = self._parent()

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
        if parent is not None and parent._schema_update_hook is not None:
            parent._schema_update_hook()

    def add_validator(self, func, attr=None, *, name=None):
        schema = self._dict
        old_validators = copy(schema.get("validators", None))
        ok = False
        parent = self._parent()
        try:
            self._add_validator(func, attr, from_meta=False,name=name)
            if parent is not None:
                parent.validate(full = False)
            ok = True
        finally:
            if not ok:
                schema.pop("validators", None)
                if old_validators is not None:
                    schema["validators"] = old_validators


    def __delattr__(self, attribute):
        self.pop(attribute)

    def __setattr__(self, attribute, value):
        if isinstance(value, SchemaWrapper):
            value = value._dict        
        self._dict[attribute] = value
        self._exported_update_hook()

    def _exported_update_hook(self):
        parent = self._parent()
        if parent is not None:
            parent.validate(accept_none=True)
        if self._update_hook is not None:
            self._update_hook()

    def __setitem__(self, item, value):
        setattr(self, item, value)

    def __getattribute__(self, attribute):
        if attribute == "dict": #TODO: property with docstring
            return super().__getattribute__("_dict")
        if attribute in ("pop", "copy", "update", "add_validator"):
            return super().__getattribute__(attribute)
        if isinstance(attribute, str) and attribute.startswith("_"):
            return super().__getattribute__(attribute)
        return self._get(attribute)

    def __getitem__(self, item):
        return getattr(self, item)

    def __repr__(self):
        return pformat(self._dict)

    def __str__(self):
        return pformat(self._dict)

from .SilkBase import compile_function