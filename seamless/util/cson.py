from copy import deepcopy

from . import pycson
pycson.loads

def cson2json(cson):
    if cson is None:
        return None
    result = pycson.loads(cson)
    if result is cson:
        result = deepcopy(cson)
    return result
