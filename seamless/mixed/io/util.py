import numpy as np

def _is_identical_dict_debug(first, second):
    keys1, keys2 = first.keys(), second.keys()
    if keys1 != keys2:
        return False
    for k in keys1:
        if not is_identical_debug(first[k], second[k]):
            return False
    return True

def _is_identical_list_debug(first, second):
    if len(first) != len(second):
        return False
    for f,s in zip(first, second):
        if not is_identical_debug(f, s):
            return False
    return True

def _is_identical_ndarray_debug(first, second):
    if first.dtype != second.dtype:
        return False
    if first.dtype.fields is None and first.dtype != np.object:
        return np.array_equal(first, second)
    elif first.dtype.fields is not None:
        for field in first.dtype.fields:
            f, s = first[field], second[field]
            if not _is_identical_ndarray_debug(f, s):
                return False
        return True
    elif first.dtype == np.object:
        for f,s in zip(first, second):
            if not is_identical_debug(f, s):
                return False
        return True
    else:
        raise TypeError(first.dtype)

def _is_identical_npvoid_debug(first, second):
    if first.dtype != second.dtype:
        return False
    if first.dtype.fields is None:
        if first.dtype == np.object:
            return is_identical_debug(first, second)
        else:
            return first == second
    else:
        for field in first.dtype.fields:
            f, s = first[field], second[field]
            if not is_identical_debug(f, s):
                return False
    return True

def is_identical_debug(first, second):
    """Checks that two mixed objects are identical
    Does not rely on any form information
    TODO: is_identical(first, form1, second, form2)"""
    if isinstance(first, dict):
        if not isinstance(second, dict):
            return False
        return _is_identical_dict_debug(first, second)
    elif isinstance(first, (tuple, list)):
        if not isinstance(second, (tuple, list)):
            return False
        return _is_identical_list_debug(first, second)
    elif isinstance(first, np.ndarray):
        if not isinstance(second, np.ndarray):
            return False
        return _is_identical_ndarray_debug(first, second)
    elif isinstance(first, np.void):
        if not isinstance(second, np.void):
            return False
        return _is_identical_npvoid_debug(first, second)
    else:
        return first == second

def mul(shape):
    result = 1
    for s in shape:
        result *= s
    return result

def addressof(obj):
    """Returns the memory address of Python object `obj`
    In CPython, this is id(x)"""
    placeholder = np.zeros(1, "O")
    placeholder[0] = obj
    placeholder2 = np.frombuffer(placeholder, np.uint64)
    return placeholder2[0]


def get_buffersize(storage, form, binary_parent=None):
    if storage == "pure-plain":
        return 0
    if storage == "pure-binary":
        type_ = form.get("type")
        if binary_parent:
            if type_ != "array":
                return 0 #already taken into account, unless Numpy array
        if type_ == "array":
            items = form["items"]
            if isinstance(items, list):
                items = items[0]
            result = items["bytesize"]
        else:
            result = form["bytesize"]
        if type_ in ("array", "tuple"):
            result *= mul(form["shape"])
        return result
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
        if type_ != "tuple":
            nbytes = form["bytesize"]
            if type_ == "array":
                nbytes *= mul(form["shape"])
            result = nbytes
        else:
            raise ValueError() #tuples must have a binary parent
    else:
        raise ValueError(storage)

    item_binary_parent = False
    if storage == "mixed-binary":
        item_binary_parent = True
    if type_ == "object":
        properties = form.get("properties", {})
        form_items = list(properties.values())
    elif type_ in ("array", "tuple"):
        form_items = form["items"]
        identical = form["identical"]
    else:
        raise ValueError(type_)

    if identical:
        assert type_ in ("array", "tuple")
        shape = form["shape"]
        if len(shape) != 1: raise NotImplementedError
        length = shape[0]
    else:
        length = len(form_items)
    for n in range(length):
        if identical:
            form_item = form_items
        else:
            form_item = form_items[n]
        substorage = storage
        if isinstance(form_item, dict):
            substorage = form_item.get("storage", storage)
        result += get_buffersize(
          substorage, form_item,
          binary_parent=item_binary_parent
        )
    return result

def get_buffersize_debug(data, storage, form, binary_parent=None):
    if storage.endswith("binary"):
        dtype_from_form = form_to_dtype(form, storage)
        data_dtype = "<None>" if not hasattr(data, "dtype") else data.dtype
        err = "\n".join(["",repr(dtype_from_form), repr(data_dtype), repr(form)])
        assert dtype_from_form == data_dtype, err
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
        if type_ != "tuple":
            result = data.nbytes
        else:
            raise ValueError() #tuples must have a binary parent
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
        properties = form.get("properties", {})
        form_items = list(properties.values())
    elif type_ in ("array", "tuple"):
        items = data
        form_items = form["items"]
        identical = form["identical"]
    else:
        raise ValueError(type_)
    if not identical:
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
        result += get_buffersize_debug(
          item, substorage, form_item,
          binary_parent=item_binary_parent
        )
    return result

def _sanitize_dtype(dtype):
    if isinstance(dtype, tuple):
        assert len(dtype) == 2
        if dtype[1] == "|O":
            return (dtype[0], '=u8')
        else:
            return dtype
    elif isinstance(dtype, list):
        return [_sanitize_dtype(d) for d in dtype]
    else:
        raise TypeError(dtype)

def sanitize_dtype(dtype):
    """Replaces Python objects with object_type in dtypes"""
    descr = _sanitize_dtype(dtype.descr)
    return np.dtype(descr,align=True)

def _form_to_dtype_scalar(form):
    type_ = form["type"]
    if type_ == "string":
        result = "S"
        result += str(form["bytesize"])
    elif type_ == "integer":
        result = "="
        if form.get("unsigned"):
            result += "u"
        else:
            result += "i"
        result += str(form["bytesize"])
    elif type_ == "number":
        result = "="
        result += "f"
        result += str(form["bytesize"])
    elif type_ == "boolean":
        result = "|b1"
    else:
        raise TypeError(type_)
    return np.dtype(result), None

def _form_to_dtype(form, storage, toplevel):
    if isinstance(form, str):
        type_ = form
    else:
        type_ = form.get("type")
    python_object = False
    if storage in ("pure-plain", "mixed-plain"):
        python_object = True
    elif type_ == "array" and not toplevel:
        python_object = True
    if python_object:
        return np.dtype("O"), None

    shape = None
    if type_ in ("string", "integer", "number", "boolean"):
        return _form_to_dtype_scalar(form)
    if type_ in ("tuple", "array"):
        assert form["identical"] #numpy arrays must be identical
        item_dtype, item_shape = _form_to_dtype(form["items"], storage, False)
        assert item_shape is None #shape must not be in items
        dtype = item_dtype
        if type_ == "tuple":
            shape = form["shape"]
    elif type_ == "object":
        assert "order" in form, form
        assert "shape" not in form #tuples of objects must have type "tuple"
        assert set(form["order"]) == set(form["properties"].keys()), form
        fields = []
        props = form["properties"]
        for field in form["order"]:
            prop = props[field]
            item_storage = prop.get("storage", storage)
            item_dtype0, item_shape = _form_to_dtype(prop, item_storage, False)
            if item_shape is None:
                item_dtype = (field, item_dtype0)
            else:
                item_dtype = (field, item_dtype0, item_shape)
            fields.append(item_dtype)
        dtype, shape = np.dtype(fields,align=True), None
    else:
        raise TypeError(type_)
    return dtype, shape

def form_to_dtype(form, storage):
    dtype, shape = _form_to_dtype(form, storage, True)
    if shape is not None:
        dtype = np.dtype(dtype, shape)
    return dtype
