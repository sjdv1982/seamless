#TODO: this is currently a stub

_known_types = [
  "object",
  "int",
  "float",
  "str",
  "bool",
  "text",
  ("text", "code", "python"),
  ("text", "code", "silk"),
  ("text", "code", "vertexshader"),
  ("text", "code", "fragmentshader"),  
  ("text", "data", "json"),
  ("text", "data", "xml"),
  ("text", "data", "silk"),
]

_constructors = {
    "object": lambda v: v,
    "int" : int,
    "float" : float,
    "bool" : bool,
    "str" : str,
    "text" : str,
}

_parsers = _constructors


def check_registered(data_type):
    return data_type in _known_types


def construct(data_type, value):
    try:
        return _constructors[data_type](value)

    except:
        raise ConstructionError


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
    if parser is None:
        return TypeError(data_type)
    try:
        return parser(value)
    except:
        raise ParseError(value)


def serialize(data_type, value):
    if data_type == "object":
        return value
    else:
        return str(value)


class ParseError(Exception):
    pass


class ConstructionError(Exception):
    pass

def register(*args, **kwargs):
    pass

from .objects import data_type_to_data_object
