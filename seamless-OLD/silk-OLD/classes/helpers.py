import numpy as np
import copy

def _prop_setter_any(child, value): return child.set(value)


def _prop_setter_json(child, value):
    return child.set(value, prop_setter=_prop_setter_json)

def _lenarray_copypad(new_arr, new_shape, old_arr, old_shape):
    assert len(new_arr)
    assert len(old_arr)
    assert len(new_shape) == len(old_shape)
    assert len(new_shape) > 0

    new_arr[0] = old_arr[0]
    if len(new_shape) == 1:
        return
    new_subsize = _get_lenarray_size(new_shape[1:])
    old_subsize = _get_lenarray_size(old_shape[1:])
    for n in range(min(old_shape[0], new_shape[0])):
        nn_new = 1 + n * new_subsize
        nn_old = 1 + n * old_subsize
        _lenarray_copypad(
            new_arr[nn_new:nn_new+new_subsize],
            new_shape[1:],
            old_arr[nn_old:nn_old+old_subsize],
            old_shape[1:],
        )

def _get_lenarray_size(shape):
    assert len(shape) > 0
    if len(shape) == 1:
        return 1
    return shape[0] * _get_lenarray_size(shape[1:]) + 1

def _get_lenarray_empty(shape):
    size = _get_lenarray_size(shape)
    arr = np.zeros(size,dtype=np.uint32)
    return arr

def _get_lenarray_full(shape, arr=None):
    if arr is None:
        arr = _get_lenarray_empty(shape)
    arr[0] = shape[0]
    if len(shape) == 1:
        return arr
    subsize = _get_lenarray_size(shape[1:])
    for n in range(shape[0]):
        nn = 1 + n * subsize
        _get_lenarray_full(shape[1:], arr[nn:nn+subsize])
    return arr

def _set_numpy_ele_prop(silkobj, prop, value, data=None):
    if data is None:
        data = silkobj._data
    if value is None: #  and optional, has been checked
        data["HAS_" + prop] = False
        return
    else:
        pdtype = data.dtype
        if not isinstance(prop, int):
            pdtype = pdtype[prop]
        if pdtype.kind in ('S', 'U'):
            itemsize1 = np.dtype(pdtype.kind+"1").itemsize
            maxlen = int(pdtype.itemsize / itemsize1)
            if pdtype.kind == 'S':
                if isinstance(value, bytes):
                    pass
                else:
                    value = str(value)
                if isinstance(value, str):
                    value = value.encode('UTF-8')
            else: #'U'
                if not isinstance(value, str):
                    value = str(value)
            if len(value) > maxlen:
                msg = "Length of string is %d, maximum length in \
    numpy representation is %d"
                raise ValueError(msg % (len(value), maxlen))
    if silkobj._props[prop]["optional"]:
        data["HAS_" + prop] = True
    data[prop] = value


def _set_numpy_ele_range(silkobj, start, end, value, arity, data=None):
    assert end-start == len(value)
    p = silkobj._data
    backup_data = p[start:end]
    ok = False
    try:
        if p.dtype.kind in ('S', 'U'):
            for n in range(len(value)):
                if arity == 1:
                    _set_numpy_ele_prop(silkobj, start+n, value[n], data)
                else:
                    _set_numpy_ele_range(silkobj, 0, len(value[n]), value[n], arity-1, data)
        else:
            p[start:end] = value
        ok = True
    finally:
        if not ok:
            p[start:end] = backup_data


def _get_numpy_ele_prop(silkobj, prop, length=None):
    d = silkobj._data
    if length is not None:
        d = d[:length]
    value = d[prop]
    if silkobj._props[prop]["optional"]:
        if not d["HAS_" + prop]:
            return None

    if value.dtype.kind == "S":
        return bytes(value).decode()
    elif value.dtype.kind == "U":
        return str(value)
    else:
        return value

def _filter_json(json, obj=None):
    if getattr(obj, "_is_none", False):
        return None
    if isinstance(json, dict):
        ret = {}
        for k in json:
            try:
                sub_obj = getattr(obj, k)
                if sub_obj is None:
                    continue
            except Exception:
                sub_obj = None
            v = _filter_json(json[k], sub_obj)
            if v is not None:
                ret[k] = v
        if not len(ret):
            return None
        return ret
    elif isinstance(json, list):
        ret = []
        for knr,k in enumerate(json):
            try:
                sub_obj = obj[knr]
                if sub_obj is None:
                    continue
            except Exception:
                sub_obj = None
            v = _filter_json(k, sub_obj)
            if v is not None:
                ret.append(v)
        if not len(ret):
            return None
        return ret
    elif isinstance(json, np.ndarray):
        raise ValueError
    else:
        return json

def _update_ptr(arr):
    fields = arr.dtype.fields
    if fields is None:
        return
    for field in fields:
        if not field[0].isupper():
            sub_arr = arr[field]
            _update_ptr(sub_arr)
        if not field.startswith("PTR_"):
            continue
        npfield = field[len("PTR_"):]
        arr[field] = arr[npfield].ctypes.data

def datacopy(arr):
    if isinstance(arr, np.ndarray):
        arr2 = copy.deepcopy(arr)
        _update_ptr(arr2)
        return arr2
    elif isinstance(arr, np.void):
        return copy.deepcopy(arr)
    raise TypeError(type(arr))
