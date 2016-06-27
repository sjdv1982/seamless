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

def check_registered(datatype):
    return datatype in _known_types

def construct(datatype, value):
    try:
        return _constructors[datatype](value)
    except:
        raise ConstructionError

def parse(datatype, value, trusted):
    try:
        return _parsers[datatype](value)
    except:
        raise ParseError

def serialize(datatype, value):
    return str(value)

class ParseError(Exception):
    pass

class ConstructionError(Exception):
    pass

from .objects import datatype_to_dataobject
