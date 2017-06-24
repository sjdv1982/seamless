#TODO: this is currently a stub

import json
import functools
import numpy as np

class TransportedArray:
    def __init__(self, array, store=None):
        assert isinstance(array, np.ndarray)
        from .gl import GLStoreBase
        if store is not None:
            assert isinstance(store, GLStoreBase)
        self.array = array
        self.store = store

_known_types = [
  "object",
  "dtype",
  "int",
  "float",
  "str",
  "bool",
  "text",
  ("text", "code", "python"),
  ("text", "code", "ipython"),
  ("text", "code", "silk"),
  ("text", "code", "slash-0"),
  ("text", "code", "vertexshader"),
  ("text", "code", "fragmentshader"),
  ("text", "html"),
  "json",
  "cson",
  "xml",
  #"silk",
  "array",
  "signal"
]

def validate_dtype(data):
    if isinstance(data, str):
        return
    elif isinstance(data, (list, tuple)):
        for d in data:
            validate_dtype(d)
    else:
        return TypeError(d)

def construct_dtype(data):
    validate_dtype(data)
    return json.dumps(data)

def bool_constructor(data):
    if data in (False, "False", 0, "0"):
        return False
    elif data in (True, "True", 1, "1"):
        return True
    else:
        return bool(int(data))

def json_constructor(data):
    from ..silk.classes import SilkObject
    if isinstance(data, SilkObject):
        data = data.json()
    return json.dumps(data, indent=2)

def cson_constructor(data):
    from ..silk.classes import SilkObject
    if isinstance(data, SilkObject):
        data = data.json()
        return json.dumps(data, indent=2)
    elif isinstance(data, (str, bytes)):
        return data
    else:
        try:
            result = json.dumps(data, indent=2)
            return result
        except Exception:
            return data

def construct_array(data):
    if isinstance(data, TransportedArray):
        return data.array
    assert isinstance(data, np.ndarray)
    return data

def signal_error(data):
    raise TypeError("Cannot construct signal")

_constructors = {
    "object": lambda v: v,
    "array": construct_array,
    "dtype": construct_dtype,
    "int" : int,
    "float" : float,
    "bool" : bool_constructor,
    "str" : str,
    "text" : str,
    "json": json_constructor,
    "cson": cson_constructor,
    "xml": str, #TODO
    "silk": str, #TODO
    "signal": signal_error,
}

_parsers = _constructors.copy()

def tuplify(data):
    if isinstance(data, str):
        return data
    elif isinstance(data, (list, tuple)):
        return tuple([tuplify(d) for d in data])
    else:
        raise TypeError(data)

def dtype_parser(data):
    return tuplify(json.loads(data))

def json_parser(data):
    from ..silk.classes import SilkObject
    if isinstance(data, str) or isinstance(data, bytes):
        if len(data) == 0:
            return None
        else:
            return json.loads(data)
    elif isinstance(data, SilkObject):
        return data.json()
    else:
        jdata = json.dumps(data)
        return json.loads(jdata)

def cson_parser(data):
    from ..silk.classes import SilkObject
    if isinstance(data, str) or isinstance(data, bytes):
        return data
    if isinstance(data, SilkObject):
        data = data.json()
    return json.dumps(data, indent=2)

_parsers["dtype"] = dtype_parser
_parsers["json"] = json_parser
_parsers["cson"] = cson_parser

def check_registered(data_type):
    return data_type in _known_types


def construct(data_type, value):
    dtype = data_type
    if isinstance(dtype, tuple) and dtype not in _constructors and \
      dtype[0] in _constructors:
        dtype = dtype[0]
    try:
        return _constructors[dtype](value)
    except Exception:
        raise ConstructionError(dtype)


def parse(data_type, value, trusted):
    parser = None
    if isinstance(data_type, str):
        parser = _parsers.get(data_type, None)
    elif isinstance(data_type, tuple) and len(data_type):
        data_type0 = data_type
        while len(data_type0) > 1:
            data_type0 = data_type0[:-1]
            parser = _parsers.get(data_type0, None)
            if parser is not None:
                break
        if parser is None:
            parser = _parsers.get(data_type[0], None)
    val = str(value)
    if parser is None:
        return TypeError(data_type)
    try:
        return parser(value)
    except Exception:
        if len(val) > 100:
            raise ParseError(val[:50] + "..." + val[-50:])
        else:
            raise ParseError(value)


def serialize(data_type, value):
    dtype = data_type
    if isinstance(dtype, tuple):
        dtype = dtype[0]

    if dtype == "object":
        return value
    elif dtype == "array":
        assert isinstance(value, np.ndarray)
        return value
    elif dtype == "dtype":
        return construct_dtype(value)
    elif dtype == "json":
        return json_constructor(value)
    elif dtype == "cson":
        return cson_constructor(value)
    elif dtype == "xml":
        raise NotImplementedError
    elif dtype == "silk":
        raise NotImplementedError
    elif dtype == "signal":
        raise TypeError(dtype)
    else:
        return str(value)


class ParseError(Exception):
    pass


class ConstructionError(Exception):
    pass

def register(type, *args, **kwargs):
    #STUB!
    _known_types.append(type)
    if isinstance(type, tuple) and type[0] == "json":
        cson_type = ("cson",) + type[1:]
        _known_types.append(cson_type)

from .objects import data_type_to_data_object
