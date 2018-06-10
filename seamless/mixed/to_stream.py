import json
import numpy as np
from copy import deepcopy

def _get_buffersize(data, storage, form, binary_parent=False):
    if storage == "pure-plain":
        return 0
    if storage == "pure-binary":
        if binary_parent:
            type_ = form.get("type")
            if type_ != "array":
                return 0 #already taken into account, unless Numpy array
        return data.nbytes
    if isinstance(form, str):
        return 0 #scalar or empty child of a mixed parent; even if binary, already taken into account
    type_ = form["type"]
    identical = False
    if type_ in ("string", "integer", "number", "boolean", "null"):
        return 0 #scalar child of a mixed parent; even if binary, already taken into account

    result = 0
    if storage == "mixed-plain":
        result = 0
    elif storage == "mixed-binary":
        result = data.nbytes
    else:
        raise ValueError(storage)

    item_binary_parent = False
    if storage == "mixed-binary":
        item_binary_parent = True
    if type_ == "object":
        if storage == "mixed-binary":
            items = [data[field] for field in data.dtype.fields]
        else:
            items = list(data.values())
        form_items = list(form["properties"].values())
    elif type_ == "array":
        items = data
        form_items = form["items"]
        identical = form["identical"]
    else:
        raise ValueError(type_)
    if identical:
        assert len(items) == len(form_items), (data, form)
    for n in range(len(items)):
        item = items[n]
        if identical:
            form_item = form_items
        else:
            form_item = form_items[n]
        substorage = storage
        if isinstance(form_item, dict):
            substorage = form_item.get("storage", storage)
        result += _get_buffersize(
          item, substorage, form_item,
          binary_parent=item_binary_parent
        )
    return result

def to_stream(data, storage, form):
    if storage == "pure-plain":
        txt = json.dumps(data, sort_keys=True, indent=2)
        return txt.encode("utf-8")
    jsons = []
    buffersize = _get_buffersize(data, storage, form)
    updated_form = deepcopy(form)

    print("BUF", buffersize)
