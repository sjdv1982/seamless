"""
Paradigm:
- get_form_XXX as long as the data is in plain storage mode
- When we encounter a numpy array Q, we go into binary storage mode:
    - First determine the form based on dtype: get_tform_XXX
    - Skip Python objects inside the dtype (storage = None)
    - Then, visit (= fill in) those Python objects using the data: visit_typedef_XXX
    - Re-enter plain mode as soon as we encounter these Python objects: get_form_XXX
    - After each Python object, leave plain-mode and return to binary
    - After finishing the Numpy array Q, leave binary mode and return to plain
"""
import numpy as np
from numpy import ndarray, void
from copy import deepcopy
from . import ( Scalar,
  _array_types, _integer_types, _float_types, _string_types, _unsigned_types
)
_string_types = (str,)  ##JSON cannot deal with bytes

dt_builtins = (
    np.dtype("bool"),
    np.dtype("int8"),
    np.dtype("int16"),
    np.dtype("int32"),
    np.dtype("int64"),
    np.dtype("uint8"),
    np.dtype("uint16"),
    np.dtype("uint32"),
    np.dtype("uint64"),
    np.dtype("float32"),
    np.dtype("float64"),
)
def is_contiguous(data):
    """Returns if the data is C-contiguous
    The last stride must be itemsize (bytesize),
     the second-last must be itemsize * shape[-1], etc.
    These criteria are stricter than Numpy's c_contiguous:
      see the documentation of numpy.ndarray.flags for an explanation
    """
    if not data.flags["C_CONTIGUOUS"]:
        return False
    stride = data.itemsize
    contiguous = False
    for n in range(data.ndim-1, -1, -1):
        if data.strides[n] != stride:
            break
        stride *= data.shape[n]
    else:
        contiguous = True
    return contiguous

def is_unsigned(dt):
    return any([dt == t for t in _unsigned_types])

def get_typedef_scalar(value):
    if isinstance(value, bool):
        typedef = "boolean"
    elif isinstance(value, _integer_types):
        typedef = "integer"
    elif isinstance(value, _float_types):
        typedef = "number"
    elif isinstance(value, _string_types):
        typedef = "string"
    elif value is None:
        typedef = "null"
    else:
        raise TypeError(type(value))
    return typedef


def visit_typedef_numpy_items(item_typedef, data):
    #numpy items of mixed-binary storage
    identical = True
    items = item_typedef
    items2 = []
    for d in data:
        item_typedef_curr = deepcopy(item_typedef)
        _ = visit_typedef_numpy("mixed-binary", item_typedef_curr, d)
        items2.append(item_typedef_curr)
    items = items2[0]
    for item_typedef_curr in items2[1:]:
        if item_typedef_curr != items2[0]:
            identical = False
            items = items2
            break
    return items, identical

def visit_typedef_numpy_tuple(storage0, typedef, data):
    # An Numpy tuple field of mixed-binary
    assert storage0 == "mixed-binary" #If None, call visit_typedef_numpy instead
    assert typedef["identical"]
    assert typedef["type"] == "tuple"

    assert data.shape == typedef["shape"]
    item_typedef = typedef["items"]
    items, identical = visit_typedef_numpy_items(item_typedef, data)
    typedef["identical"] = identical
    typedef["item_storage"] = item_storage
    typedef["items"] = item_typedef
    return "mixed-binary"

def visit_typedef_numpy_struct(storage0, typedef, data):
    assert "properties" in typedef ##since type is "object"
    props = typedef["properties"]
    storage = "pure-binary"
    for k in props:
        subtypedef = props[k]
        if not "storage" in subtypedef:
            continue
        subdata = data[k]
        substorage0 = subtypedef["storage"]
        substorage = visit_typedef_numpy(substorage0, subtypedef, subdata)
        if substorage0 is None or substorage != "pure-binary":
            storage = "mixed-binary"
        subtypedef["storage"] = substorage
    if storage == "mixed-binary":
        for k in props:
            subtypedef = props[k]
            substorage = subtypedef.get("storage")
            if substorage is None:
                subtypedef["storage"] = "pure-binary"
            elif substorage == "mixed-binary":
                subtypedef.pop("storage")
    return storage

def visit_typedef_numpy(storage0, typedef, data):
    #visit and fill in mixed-binary typedefs
    if storage0 is None: #typedef of a Python object inside Numpy
        assert not isinstance(data, void), type(data)
        if isinstance(typedef, dict) and "items" in typedef:
            assert typedef["items"] is None
            storage = "mixed-binary"
            if typedef["type"] in ("array", "tuple"): # Numpy array of Python objects
                if typedef["type"] == "tuple": # Numpy multi-element field of Python objects
                    assert data.shape == typedef["shape"]
                item_storage, item_typedef = [], []
                for d in data: #TODO: multi-dimensional (currently NotImplementedError)
                    curr_item_storage, curr_item_typedef = get_form_python_inside_numpy(d)
                    item_storage.append(curr_item_storage)
                    item_typedef.append(curr_item_typedef)
                for dnr, d in enumerate(data[1:]):
                    if item_storage[dnr] != item_storage[0] or \
                      item_typedef[dnr] != item_typedef[0]:
                        identical = False
                        break
                else:
                    identical = True
                    item_storage = item_storage[0]
                    item_typedef = item_typedef[0]
                typedef["identical"] = identical
                typedef["item_storage"] = item_storage
                typedef["items"] = item_typedef
            else:
                raise TypeError(typedef["type"])
        else: # Python object inside a Numpy structured dtype
            if isinstance(data, ndarray):
                storage, typedef2 = get_form_list(data)  #plain storage
            else:
                storage, typedef2 = get_form_python_inside_numpy(data)  #plain storage
            if isinstance(typedef2, dict):
                typedef.clear()
                typedef.update(typedef2)
            else:
                typedef = typedef2
    elif storage0 == "mixed-binary":
        assert isinstance(data, (ndarray, void)), type(data)
        assert isinstance(typedef, dict), type(typedef)
        if typedef["type"] == "object":
            return visit_typedef_numpy_struct(storage0, typedef, data)
        elif typedef["type"] == "array":
            raise Exception #should be impossible: arbitrary-length Numpy arrays inside Numpy dtypes are Python objects (storage0 = None)!
        elif typedef["type"] == "tuple":
            return visit_typedef_numpy_tuple(storage0, typedef, data)
        else:
            raise TypeError(typedef["type"])
    else:
        raise ValueError(storage0)
    return storage

def get_form_python_inside_numpy(data):
    if isinstance(data, list):
        return get_form_list_plain(data)
    elif isinstance(data, dict):
        return get_form_dict_plain(data)
    elif isinstance(data, _string_types):
        return "pure-plain", "string"
    elif data is None:
        return "pure-plain", "null"
    else:
        raise TypeError(type(data)) #must be list, dict, string or None; scalar Python objects not allowed

def get_tform_numpy_pyobject(dt):
    if dt.ndim:
        if dt.ndim > 1: raise NotImplementedError #TODO: multi-dimensional Python tuples
        storage = None #technically, mixed-binary, but this will be visited
        typedef = {
            "type": "tuple",
            "items": None, #to be visited
            "shape": dt.shape,
        }
    else:
        storage, typedef = None, None #to be visited
    return storage, typedef

def get_tform_numpy_builtin(dt):
    dtb = dt.base
    if dtb == object:
        return get_tform_numpy_pyobject(dt)

    storage = "pure-binary"
    if dtb == bool:
        typedef0 = "boolean"
    elif any([dtb == t for t in _integer_types]):
        typedef0 = "integer"
    elif any([dtb == t for t in _float_types]):
        typedef0 = "number"
    elif is_np_str(dtb):
        typedef0 = "string"
    else:
        raise TypeError(dtb)

    typedef = {
        "type": typedef0,
        "bytesize": dt.itemsize,
    }
    if typedef0 == "integer":
        unsigned = is_unsigned(dt)
        typedef["unsigned"] = unsigned
    if dt.ndim:
        typedef = {
            "type": "tuple",
            "items": typedef,
            "identical": True,
            "shape": dt.shape,
        }
    return storage, typedef

def get_tform_numpy_struct(dt):
    if not dt.isalignedstruct:
        raise TypeError("Composite dtypes must be memory-aligned", dt)
    if not dt.isnative:
        raise TypeError("Composite dtypes must be native")
    storages = {}
    props = {}
    typedef = {"type": "object", "properties": props, "bytesize": dt.itemsize}
    typedef["order"] = list(dt.fields)
    for fieldname in dt.fields:
        cstorage, ctypedef = get_tform_numpy(dt[fieldname])
        storages[fieldname] = cstorage
        props[fieldname] = ctypedef
    storage_set = set(storages.values())
    if len(storage_set) == 1 and storage_set.pop() == "pure-binary":
        storage = "pure-binary"
    else:
        storage = "mixed-binary"
        for fieldname in dt.fields:
            cstorage = storages[fieldname]
            if cstorage == "pure-binary":
                continue
            ctypedef = props[fieldname]
            if ctypedef is None or isinstance(ctypedef, str):
                ctypedef = {"type": ctypedef}
                props[fieldname] = ctypedef
            ctypedef["storage"] = cstorage
    if dt.ndim:
        typedef["storage"] = storage
        typedef = {
            "type": "tuple",
            "shape": dt.shape,
            "items":  typedef,
            "identical": True
        }
    return storage, typedef


def is_np_str(dt):
    return dt == np.dtype("S%d" % dt.itemsize)

def get_tform_numpy(dt):
    if dt.base.isbuiltin or is_np_str(dt) or dt in dt_builtins:
        return get_tform_numpy_builtin(dt)
    return get_tform_numpy_struct(dt)

def get_form_dict_plain(data):
    typedef = {"type": "object"}
    if not len(data):
        return "pure-plain", typedef
    props = {}
    typedef["properties"] = props
    storages = {}
    for k,v in data.items():
        cstorage, ctypedef = get_form(v)
        props[k] = ctypedef
        storages[k] = cstorage
    storage_set = set(storages.values())
    if len(storage_set) == 1 and storage_set.pop() == "pure-plain":
        storage = "pure-plain"
    else:
        storage = "mixed-plain"
        for fieldname in data:
            cstorage = storages[fieldname]
            if cstorage == "pure-plain":
                continue
            ctypedef = props[fieldname]
            if isinstance(ctypedef, str):
                ctypedef = {"type": ctypedef}
                props[fieldname] = ctypedef
            ctypedef["storage"] = cstorage
    return storage, typedef

def get_form_dict(data):
    if isinstance(data, Scalar):
        raise TypeError
    elif isinstance(data, void):
        dt = data.dtype
        storage, typedef = get_tform_numpy(dt)
        if storage in (None, "mixed-binary"):
            storage = visit_typedef_numpy(storage, typedef, data)
    elif isinstance(data, _array_types):
        raise TypeError
    elif isinstance(data, dict):
        storage, typedef = get_form_dict_plain(data)
    else:
        raise TypeError
    return storage, typedef

def get_form_items_numpy(data):
    dt = data.dtype
    storage, item_typedef = get_tform_numpy(dt)
    identical = True
    items = item_typedef
    if storage == "pure-binary":
        pass
    elif storage == "mixed-binary":
        items, identical = visit_typedef_numpy_items(item_typedef, data)
    elif storage is None: #pyobject
        return None, item_typedef, True #Will be visited later
    else:
        raise ValueError(storage)
    return storage, items, identical

def get_form_items_list_plain(data):
    identical = True
    storages = []
    items2 = []
    for d in data:
        item_storage, item_typedef = get_form(d)
        storages.append(item_storage)
        items2.append(item_typedef)

    storage_set = set(storages)
    if len(storage_set) > 1:
        different = True
    else:
        different = False
        for item_typedef in items2[1:]:
            if item_typedef != items2[0]:
                different = True
                break
    if different:
        items = items2
        identical = False
        if len(storage_set) == 1 and storage_set.pop() == "pure-plain":
            storage = "pure-plain"
        else:
            storage = "mixed-plain"
        for n in range(len(data)):
            s = storages[n]
            if s == "pure-plain":
                continue
            ctypedef = items[n]
            if isinstance(ctypedef, str):
                ctypedef = {"type": ctypedef}
                items[n] = ctypedef
            items[n]["storage"] = s
    else:
        if not len(items2):
            storage = "pure-plain"
            items = None
        else:
            items = items2[0]
            child_storage = storages[0]
            if child_storage == "pure-plain":
                storage = "pure-plain"
            else:
                storage = "mixed-plain"
                if isinstance(items, str):
                    items = {"type": items}
                items["storage"] = child_storage
    return storage, items, identical

def get_form_list(data):
    extra = {}
    if isinstance(data, ndarray):
        dt = data.dtype
        if not dt.isnative:
            raise TypeError("dtypes must be native")
        storage, items, identical = get_form_items_numpy(data)
        extra = {
            "shape": data.shape,
        }
        strides = data.strides
        contiguous = is_contiguous(data)
        extra["contiguous"] = contiguous
        if not contiguous:
            extra["strides"] = strides
    elif isinstance(data, _array_types):
        storage, items, identical = get_form_items_list_plain(data)
        extra = {
            "shape": (len(data),),
        }
    elif isinstance(data, dict):
        raise TypeError
    elif isinstance(data, Scalar):
        raise TypeError
    elif isinstance(data, void):
        raise TypeError
    else:
        raise TypeError

    typedef = {
        "type": "array",
        "items": items,
        "identical": identical
    }
    typedef.update(extra)
    return storage, typedef

def get_form_list_plain(data):
    #data must be a plain list
    storage, items, identical = get_form_items_list_plain(data)
    typedef = {
        "type": "array",
        "items": items,
        "identical": identical,
        "shape": (len(data),),
    }
    return storage, typedef


def get_form(data):
    if isinstance(data, bytes):
        data = np.array(data)
    if isinstance(data, Scalar):
        storage, typedef = "pure-plain", get_typedef_scalar(data)
    elif isinstance(data, void):
        dt = data.dtype
        storage, typedef = get_tform_numpy(dt)
        if storage in (None, "mixed-binary"):
            storage = visit_typedef_numpy(storage, typedef, data)
    elif isinstance(data, _array_types):
        storage, typedef = get_form_list(data)
    elif isinstance(data, dict):
        storage, typedef = get_form_dict_plain(data)
    else:
        raise TypeError(type(data))
    return storage, typedef
