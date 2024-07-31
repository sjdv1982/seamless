from copy import deepcopy
import subprocess
from subprocess import PIPE
import json

import cson as cson_lib
cson_lib.loads

def cson2json(cson):
    if cson is None:
        return None
    result = cson_lib.loads(cson)
    if result is cson:
        result = deepcopy(cson)
    return result
