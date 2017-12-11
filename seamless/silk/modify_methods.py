from .validation import _array_types
from functools import partial

def list_grow_method(self, name, *args, **kwargs):
    empty_list = (
        isinstance(self.data,list) and \
        len(self.data) == 0
    )
    item = None
    item_schema = None
    if name == "append":
        item, = args
    elif name == "insert":
        _, item = args
    if item is not None:
        if isinstance(item, Silk):
            item_schema = item.schema.dict

    method = self._get(name, skip_modify_methods = True)

    result = method(*args, **kwargs)
    if self._forks is None or self._forks[-1].validate:
        self.validate()
    if empty_list:
        self._infer_list_item(item_schema)
    return result

def list_modify_method(self, name, *args, **kwargs):
    #TODO: special case for numpy arrays, including resize() if needed,
    #   but need a path from the parent!
    method = self._get(name, skip_modify_methods = True)
    result = method(*args, **kwargs)
    if self._forks is None or self._forks[-1].validate:
        self.validate()

def dict_modify_method(self, name, *args, **kwargs):
    #TODO: special case for numpy arrays, including astype() if needed,
    #   but need a path from the parent!
    method = self._get(name, skip_modify_methods = True)
    result = method(*args, **kwargs)
    if self._forks is None or self._forks[-1].validate:
        self.validate()

_list_grow_method_names = set(("append", "extend", "insert"))
_list_modify_method_names = set(("clear", "pop", "remove", "reverse", "sort"))
_dict_modify_method_names = set(("clear", "pop", "popitem", "update"))

def try_modify_methods(self, method):
    """Tries if "method" is a data-modifying method
    Returns:
        is_modifying_method: bool
        result: partial method
    """
    if isinstance(self.data, _array_types):
        if method in _list_grow_method_names:
            result = partial(list_grow_method, self, method)
            return True, result
        elif method in _list_modify_method_names:
            result = partial(list_modify_method, self, method)
            return True, result
        else:
            return False, None
    elif isinstance(self.data, dict):
        if method in _dict_modify_method_names:
            result = partial(dict_modify_method, self, method)
            return True, result
        else:
            return False, None
    else:
        return False, None

from .Silk import Silk
