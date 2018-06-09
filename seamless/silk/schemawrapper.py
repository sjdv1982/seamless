import weakref
from pprint import pformat

class SchemaWrapper:
    _update_hook = None
    def __init__(self, _parent, _dict, _update_hook):
        super().__setattr__("_parent", weakref.ref(_parent))
        if isinstance(_dict, SchemaWrapper):
            _dict = _dict.dict
        super().__setattr__("_dict", _dict)
        if _update_hook is not None:
            super().__setattr__("_update_hook", _update_hook)

    def _get(self, attribute):
        child = self._dict.get(attribute, None)
        if child is None:
            props = self._dict.get("properties", None)
            if props is None:
                raise AttributeError(attribute)
            child = props.get(attribute, None)
            if child is None:
                raise AttributeError(child)
        return SchemaWrapper(self._parent(), child, self._update_hook)

    def __setattr__(self, attribute, value):
        if isinstance(value, SchemaWrapper):
            value = value.dict
        self._dict[attribute] = value
        parent = self._parent()
        if parent is not None:
            parent.validate()
        if self._update_hook is not None:
            self._update_hook()

    def __setitem__(self, item, value):
        setattr(self, item, value)

    def __getattribute__(self, attribute):
        if attribute == "dict":
            return super().__getattribute__("_dict")
        if isinstance(attribute, str) and attribute.startswith("_"):
            return super().__getattribute__(attribute)
        return self._get(attribute)

    def __getitem__(self, item):
        return getattr(self, item)

    def __repr__(self):
        return pformat(self._dict)

    def __str__(self):
        return pformat(self._dict)
