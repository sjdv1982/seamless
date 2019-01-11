from .validation import _array_types
from functools import partial

def list_grow_method(self, name, *args, **kwargs):
    item = None
    item_schema = None
    if name == "append":
        item, = args
        pos = len(self)
    elif name == "insert":
        pos, item = args
    if item is not None:
        if isinstance(item, Silk):
            item_schema = item.schema.dict

    method = self._get_special(name, skip_modify_methods = True)

    if isinstance(item, Silk):
        item_schema = item.schema.dict
        item = item.data

    schema = self._schema
    schema_updated = self._infer_new_item(
       schema, pos, item, value_item_schema=item_schema
    )

    result = method(*args, **kwargs)
    if not len(self._forks):
        self.validate()
    if schema_updated and self._schema_update_hook is not None:
        self._schema_update_hook()
    return result

def list_modify_method(self, name, *args, **kwargs):
    #TODO: special case for numpy arrays, including resize() if needed,
    #   but need a path from the parent!
    method = self._get_special(name, skip_modify_methods = True)
    result = method(*args, **kwargs)
    if not len(self._forks):
        self.validate()

def dict_modify_method(self, name, *args, **kwargs):
    #TODO: special case for numpy arrays, including astype() if needed,
    #   but need a path from the parent!
    method = self._get_special(name, skip_modify_methods = True)
    result = method(*args, **kwargs)
    if not len(self._forks):
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
