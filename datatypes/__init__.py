#TODO: this is currently a stub

_known_types = [
  "int",
  "float",
  "str",
  "bool",
  "text",
  ("text", "code", "python"),
  ("text", "code", "spyder"),
  ("text", "data", "json"),
  ("text", "data", "xml"),
  ("text", "data", "spyder"),
]

_constructors = {
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
    try:
        return _parsers[data_type](value)
    except:
        raise ParseError


def serialize(data_type, value):
    return str(value)


class ParseError(Exception):
    pass


class ConstructionError(Exception):
    pass


from .objects import data_type_to_data_object
