import json
import numpy as np
from io import BytesIO
import ctypes

from .. import MAGIC_SEAMLESS
from .util import get_buffersize, form_to_dtype, mul

def _load_from_buffer(storage, form, buffer, buffer_offset, buffersize, shape):
    dtype = form_to_dtype(form, storage)
    shape0 = (1,)
    if shape is not None:
        shape0 = shape
    assert dtype.itemsize * mul(shape0) == buffersize, (dtype.itemsize, shape0, buffersize)
    data = np.empty(shape0,dtype)
    # If dtype contains objects, they will be initialized to None,
    #  and refcounts to None will be increased by Numpy
    # memmove will replace them in a dirty manner, which will not decref None,
    #  but this is harmless
    ctypes.memmove(
      data.ctypes.data,
      buffer.ctypes.data + buffer_offset,
      buffersize
    )
    if shape is None:
        data = data[0]
    return data

def _from_stream_binary(
  data, form,
  jsons, buffer
):
    #print("_from_stream_binary", form, data)
    storage = "mixed-binary"
    type_ = form["type"]
    if type_ == "object":
        if data is None:
            buffer_offset = jsons[0].pop(0)
            buffersize = jsons[0][0] - buffer_offset
            data = _load_from_buffer(
              storage, form, buffer, buffer_offset, buffersize, None
            )
        keys = form["order"]
        for key in keys:
            item_form = form["properties"][key]
            if not isinstance(item_form, dict):
                continue #scalar
            item_storage = item_form.get("storage", "pure-binary")
            _from_stream_sub(data, key, item_storage, item_form, jsons, buffer)
    elif type_ in ("tuple", "array"):
        if data is None:
            buffer_offset = jsons[0].pop(0)
            buffersize = jsons[0][0] - buffer_offset
            shape = form["items"]["shape"] if type_ == "array" else form["shape"]
            my_form = form["items"]
            data = _load_from_buffer(
              storage, my_form, buffer, buffer_offset, buffersize, shape
            )
        assert len(shape) == 1
        form_items = form["items"]
        assert form["identical"]
        item_form = form_items
        if isinstance(item_form, dict):
            item_storage = item_form.get("storage", "pure-plain")
            for n in range(shape[0]):
                _from_stream_sub(data, n, item_storage, item_form, jsons, buffer)
        else:
            assert isinstance(item_form, str) #scalar
    else:
        raise TypeError(type_, form)

    return data

def _from_stream_plain(
  data, form,
  jsons, buffer
):
    #print("_from_stream_plain", form, data)
    storage = "mixed-plain"
    type_ = form["type"]
    if data is None:
        data = jsons.pop(1)
    if type_ == "object":
        for key in sorted(form["properties"]):
            item_form = form["properties"][key]
            if not isinstance(item_form, dict):
                continue #scalar
            item_storage = item_form.get("storage", "pure-plain")
            _from_stream_sub(data, key, item_storage, item_form, jsons, buffer)
    elif type_ in ("tuple", "array"):
        shape = form["shape"]
        assert len(shape) == 1
        form_items = form["items"]
        for n in range(shape[0]):
            if form["identical"]:
                item_form = form_items
            else:
                item_form = form_items[n]
            if not isinstance(item_form, dict):
                continue #scalar
            item_storage = item_form.get("storage", "pure-plain")
            _from_stream_sub(data, n, item_storage, item_form, jsons, buffer)
    else:
        raise TypeError(type_, form)
    return data

def _from_stream(
  data, storage, form,
  jsons, buffer
):
    if storage == "mixed-binary":
        return _from_stream_binary(
          data, form,
          jsons, buffer
        )
    elif storage == "mixed-plain":
        return _from_stream_plain(
          data, form,
          jsons, buffer
        )
    else:
        raise ValueError(storage)

def _from_stream_sub(
  parent_data, sub, storage, form,
  jsons, buffer
):
    if storage.endswith("plain"):
        if isinstance(parent_data, np.generic):
            my_data = jsons.pop(1)
            parent_data[sub] = my_data #fill pyobject slot
    else: #binary
        if isinstance(form, str):
            form = {"type": form}
        is_array = (form.get("type") == "array")
        if is_array or not isinstance(parent_data, np.generic):
            assert "type" in form
            type_ = form["type"]
            assert type_ in ("array", "tuple", "object")
            if type_ == "array":
                shape = form["shape"]
                my_form = form["items"]
            elif type_ == "tuple":
                my_form = form["items"]
                shape = my_form["shape"]
            else:
                my_form = form
                shape = None
            buffer_offset = jsons[0].pop(0)
            buffersize = jsons[0][0] - buffer_offset
            my_data = _load_from_buffer(
              storage, my_form, buffer, buffer_offset, buffersize, shape
            )
            parent_data[sub] = my_data

    if storage.startswith("pure"):
        return

    my_data = parent_data[sub]
    _from_stream(
      my_data, storage, form,
      jsons, buffer
    )




def from_stream(stream, storage, form):
    """Reverses to_stream, returning data"""
    if storage == "pure-plain":
        assert isinstance(stream, str)
        if isinstance(stream, str):
            txt = stream
        else:
            assert not stream.startswith(MAGIC_SEAMLESS)
            assert not stream.startswith(MAGIC_NUMPY)
            txt = stream.decode("utf-8")
        result = json.loads(txt)
        return result
    elif storage == "pure-binary":
        b = BytesIO(stream)
        arr0 = np.load(b, allow_pickle=False)
        if arr0.ndim == 0 and arr0.dtype.char != "S":
            arr = np.frombuffer(arr0,arr0.dtype)
            return arr[0]
        else:
            return arr0
    assert stream.startswith(MAGIC_SEAMLESS)
    l = len(MAGIC_SEAMLESS)
    s1 = stream[l:l+8]
    s2 = stream[l+8:l+16]
    len_jsons = np.frombuffer(s1, dtype=np.uint64).tolist()[0]
    buffersize = np.frombuffer(s2, dtype=np.uint64).tolist()[0]
    assert len(stream) == l + 16 + len_jsons + buffersize
    bytes_jsons = stream[l+16:l+16+len_jsons]
    jsons = json.loads(bytes_jsons.decode("utf-8"))
    bytebuffer = stream[l+16+len_jsons:]
    buffer = np.frombuffer(bytebuffer,dtype=np.uint8)
    data = _from_stream(
        None, storage, form,
        jsons, buffer
    )
    return data
