import json
import numpy as np
from copy import deepcopy
from io import BytesIO

from .. import MAGIC_SEAMLESS, _integer_types, _float_types, _string_types
from .util import get_buffersize, get_buffersize_debug, \
  sanitize_dtype

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
    return new_data

def _to_stream(
  data, storage, form,
  jsons, buffer, buffer_offset, binary_parent=None
):
    if storage == "pure-plain":
        if binary_parent:
            jsons.append(data) #no need to copy anything
            return -1, buffer_offset
        else: #parent is already plain (and is in jsons), nothing to do
            return None, buffer_offset
    if storage == "pure-binary":
        type_ = form.get("type")
        if binary_parent:
            if type_ != "array":
                return None, buffer_offset #already taken into account, unless Numpy array
        #plain parent, or we occopy a Python object slot in the parent Numpy struct
        my_data = _copy_into_buffer(data, buffer, buffer_offset)
        buffersize = data.nbytes
        new_buffer_offset = buffer_offset + buffersize
        jsons[0].append(new_buffer_offset)
        buffer_offset = new_buffer_offset
        return buffersize, buffer_offset
    if isinstance(form, str):
        return None, buffer_offset #scalar or empty child of a mixed parent; even if binary, already taken into account
    type_ = form["type"]
    identical = False
    if type_ in ("string", "integer", "number", "boolean", "null"):
        return None, buffer_offset #scalar child of a mixed parent; even if binary, already taken into account

    my_data = None
    my_buffersize = None
    if storage == "mixed-plain":
        if binary_parent != False:
            my_data = deepcopy(data)
            if binary_parent:
                my_buffersize = -1
            jsons.append(my_data)
        else: #data has already been copied
            my_data = data
    elif storage == "mixed-binary":
        if type_ != "tuple": #plain parent, or we occupy a Python object slot in the parent Numpy struct
            my_data = _copy_into_buffer(data, buffer, buffer_offset)
            buffersize = data.nbytes
            new_buffer_offset = buffer_offset + buffersize
            jsons[0].append(new_buffer_offset)
            buffer_offset = new_buffer_offset
            my_buffersize = buffersize
        else:
            assert binary_parent #tuples must have a binary parent
            my_data = data #data has already been buffered
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
            keys = sorted(list(my_data.keys()))
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
        item_size, buffer_offset = _to_stream(
          item, substorage, form_item,
          jsons, buffer, buffer_offset,
          binary_parent=item_binary_parent
        )
        if item_size is not None:
            assert my_data is not data
            #print("ITEM", item_size)
            my_data[keys[n]] = 0 #zero out the Python object
    return my_buffersize, buffer_offset

def to_stream(data, storage, form):
    """ Converts data to a stream of bytes (either a bytes object or a bytearray)"""
    if storage == "pure-plain":
        data = _convert_np_void(data)
        txt = json.dumps(data, sort_keys=True, indent=2)
        return txt.encode("utf-8")
    elif storage == "pure-binary":
        b = BytesIO()
        np.save(b, data, allow_pickle=False)
        return b.getvalue()
    buffer_offsets = [0]
    jsons = [buffer_offsets]
    buffersize_debug = get_buffersize_debug(data, storage, form)
    buffersize = get_buffersize(storage, form)
    assert buffersize == buffersize_debug, (buffersize, buffersize_debug)
    updated_form = deepcopy(form)

    bytebuffer = bytearray(buffersize)
    buffer = np.frombuffer(bytebuffer,dtype=np.uint8)
    id, buffer_offset = _to_stream(data, storage, updated_form, jsons, buffer, 0)
    assert buffer_offset == buffersize, (buffer_offset, buffersize)

    buffersize_check = get_buffersize(storage, updated_form)
    assert buffersize == buffersize_check, (buffersize, buffersize_check)
    #print("BUFFERSIZE", buffersize)

    bytes_jsons = json.dumps(jsons).encode("utf-8")
    s1 = np.uint64(len(bytes_jsons)).tobytes()
    s2 = np.uint64(buffersize).tobytes()
    streamsize = len(MAGIC_SEAMLESS) + 16 + len(bytes_jsons) + buffersize
    stream = bytearray(streamsize)
    l = len(MAGIC_SEAMLESS)
    stream[:l] = MAGIC_SEAMLESS
    stream[l:l+8] = s1
    stream[l+8:l+16] = s2
    stream[l+16:l+16+len(bytes_jsons)] = bytes_jsons
    stream[l+16+len(bytes_jsons):streamsize] = bytebuffer
    return stream
