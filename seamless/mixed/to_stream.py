import json
import numpy as np
from copy import deepcopy
from io import BytesIO

from . import MAGIC_SEAMLESS, _integer_types, _float_types, _string_types

print("TODO: make a _get_buffersize also for from_stream, which should arrive at the same size as the input stream buffer")

_itemsize = np.dtype(np.object).itemsize
assert _itemsize in (4, 8)
object_type = '<i4' if _itemsize == 4 else '<i8'
del _itemsize

def _convert_np_void(data):
    if not isinstance(data, np.generic):
        return data
    if isinstance(data, _integer_types):
        return int(data)
    if isinstance(data, _float_types):
        return float(data)
    if isinstance(data, _string_types):
        return str(data)
    raise TypeError(type(data))

def _sanitize_dtype(dtype):
    if isinstance(dtype, tuple):
        assert len(dtype) == 2
        if dtype[1] == "|O":
            return (dtype[0], object_type)
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

def _copy_into_buffer(data, buffer, offset):
    size = data.nbytes
    if not data.dtype.hasobject:
        new_data = buffer[offset:offset+size].view(data.dtype)
        new_data[:] = data
    else:
        rbuffer = np.frombuffer(buffer=data, dtype=np.uint8)
        buffer[offset:offset+size] = rbuffer
        clean_dtype = sanitize_dtype(data.dtype)
        new_data = buffer[offset:offset+size].view(clean_dtype)
        if isinstance(data, np.void):
            new_data = new_data[0]
    return new_data, size

def _get_buffersize(data, storage, form, binary_parent=None):
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
        form_items = list(form["properties"].values())
    elif type_ in ("array", "tuple"):
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

def _to_stream(
  data, storage, form,
  jsons, buffer, buffer_offset, binary_parent=None
):
    if storage == "pure-plain":
        if binary_parent:
            json_id = len(jsons) + 1
            jsons.append(data) #no need to copy anything
            return -json_id, 0
        else: #parent is already plain (and is in jsons), nothing to do
            return None, 0
    if storage == "pure-binary":
        type_ = form.get("type")
        if binary_parent:
            if type_ != "array":
                return None, 0 #already taken into account, unless Numpy array
        #plain parent, or we occopy a Python object slot in the parent Numpy struct
        my_data, size = _copy_into_buffer(data, buffer, buffer_offset)
        return buffer_offset, size
    if isinstance(form, str):
        return None, 0 #scalar or empty child of a mixed parent; even if binary, already taken into account
    type_ = form["type"]
    identical = False
    if type_ in ("string", "integer", "number", "boolean", "null"):
        return None, 0 #scalar child of a mixed parent; even if binary, already taken into account

    my_data = None
    my_id = None
    increment = 0
    if storage == "mixed-plain":
        if binary_parent != False:
            my_data = deepcopy(data)
            if binary_parent:
                my_id = -(len(jsons) + 1)
            jsons.append(my_data)
        else: #data has already been copied
            my_data = data
        increment = 0
    elif storage == "mixed-binary":
        if type_ != "tuple": #plain parent, or we occopy a Python object slot in the parent Numpy struct
            increment = data.nbytes
            my_data, size = _copy_into_buffer(data, buffer, buffer_offset)
        else:
            assert binary_parent #tuples must have a binary parent
            my_data = data #data has already been buffered
            increment = 0
    else:
        raise ValueError(storage)

    item_binary_parent = False
    if storage == "mixed-binary":
        item_binary_parent = True
    if type_ == "object":
        if storage == "mixed-binary":
            keys = list(my_data.dtype.fields)
            items = [my_data[field] for field in keys]
            for n in range(len(keys)):
                if isinstance(data[n], object):
                    items[n] = data[n]
        else:
            keys = list(my_data.keys())
            items = [my_data[k] for k in keys]
        form_items = [form["properties"][k] for k in keys]
    elif type_ in ("array", "tuple"):
        items = my_data
        keys = list(range(len(my_data)))
        form_items = form["items"]
        identical = form["identical"]
    else:
        raise ValueError(type_)
    keys = list(keys)
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
        item_id, item_increment = _to_stream(
          item, substorage, form_item,
          jsons, buffer, buffer_offset + increment,
          binary_parent=item_binary_parent
        )
        if item_id is not None:
            assert my_data is not data
            mt = my_data.dtype if isinstance(my_data, (np.void, np.ndarray)) else type(my_data)
            t = data.dtype if isinstance(data, (np.void, np.ndarray)) else type(data)
            my_data[keys[n]] = item_id
        increment += item_increment
    return my_id, increment

def to_stream(data, storage, form):
    if storage == "pure-plain":
        data = _convert_np_void(data)
        txt = json.dumps(data, sort_keys=True, indent=2)
        return txt.encode("utf-8")
    elif storage == "pure-binary":
        b = BytesIO()
        np.save(b, data)
        return b.getvalue()
    jsons = []
    buffersize = _get_buffersize(data, storage, form)
    updated_form = deepcopy(form)

    buffer = np.zeros(buffersize,np.uint8)
    id, increment = _to_stream(data, storage, form, jsons, buffer, 0)
    assert id is None and increment == buffersize, (id, increment, buffersize)

    bytes_jsons = json.dumps(jsons).encode("utf-8")
    s1 = np.uint64(len(bytes_jsons)).tobytes()
    s2 = np.uint64(buffersize).tobytes()
    return MAGIC_SEAMLESS + s1 + s2 + bytes_jsons + buffer.tobytes()
    """ #TODO: more efficient, like below (but assignment only copies 1 char???)
    streamsize = len(MAGIC_SEAMLESS) + 16 + len(bytes_jsons) + buffersize
    stream = np.zeros(streamsize,np.bytes_)
    l = len(MAGIC_SEAMLESS)
    stream[:l] = MAGIC_SEAMLESS
    stream[l:l+8] = s1
    stream[l+8:l+16] = s2
    stream[l+16:l+16+len(bytes_jsons)] = bytes_jsons
    stream[l+16+len(bytes_jsons):streamsize] = buffer
    return stream.tobytes()
    """
