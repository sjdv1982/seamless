from pprint import pformat

class SchemaWrapper:

    def __init__(self, _dict):
        if isinstance(_dict, SchemaWrapper):
            _dict = _dict.dict
        super().__setattr__("_dict", _dict)

    def _get(self, attribute):
        child = self._dict.get(attribute, None)
        if child is None:
            child = {}
            self._dict[attribute] = child
        return SchemaWrapper(child)

    def __setattr__(self, attribute, value):
        if isinstance(value, SchemaWrapper):
            value = value.dict
        self._dict[attribute] = value

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
