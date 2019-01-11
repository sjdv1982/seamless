import weakref
from pprint import pformat
from copy import deepcopy

from .. import Wrapper
class SchemaWrapper(Wrapper):
    _update_hook = None
    _parent = lambda self: None
    def __init__(self, _parent, _dict, _update_hook):
        if _parent is not None:
            super().__setattr__("_parent", weakref.ref(_parent))
        if isinstance(_dict, SchemaWrapper):
            _dict = _dict.dict
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
            value = value.dict
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

    def __delattr__(self, attribute):
        self.pop(attribute)

    def __setattr__(self, attribute, value):
        if isinstance(value, SchemaWrapper):
            value = value.dict
        self._dict[attribute] = value
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
        if attribute in ("pop", "copy", "update"):
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
