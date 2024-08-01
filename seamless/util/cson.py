"""Convert CoffeeScript Object Notation (CSON) to JSON"""

from copy import deepcopy

from . import pycson


def cson2json(cson):
    """Convert CoffeeScript Object Notation (CSON) to JSON"""
    if cson is None:
        return None
    result = pycson.loads(cson)
    if result is cson:
        result = deepcopy(cson)
    return result
