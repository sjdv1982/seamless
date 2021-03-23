#medium-complexity tests for mixed get_form

import sys
import numpy as np
from silk.mixed.get_form import get_form
import json

_print = print
def print(*args):
    for a in args:
        _print(json.dumps(a, indent=2, sort_keys=True), end=" ")
    _print()


dt = np.dtype([
    ("a", int),
    ("b", object),
], align=True)
data = np.zeros(2, dtype=dt)
data[0]["b"] = [1,2,3]
data[1]["b"] = [4,5,6]
storage, form = get_form(data)
print(storage, form); print()

data[1]["b"] = [4.0,5.0,6.0]
storage, form = get_form(data)
print(storage, form); print()

arr = np.zeros(10)

data = [arr, arr, arr]
storage, form = get_form(data)
print(storage, form); print()

data = [5, arr, None]
storage, form = get_form(data)
print(storage, form); print()

dt = np.dtype([
    ("a", int),
    ("b", float),
], align=True)
arr2 = np.zeros(2, dtype=dt)
data = {"arr":  arr, "arr2": arr2, "v": arr2[0], "z": 10}
storage, form = get_form(data)
print(storage, form); print()

old_data = data
dt = np.dtype([
    ("a", int),
    ("b", object),
], align=True)
data = np.zeros(1,dtype=dt)[0]
data["a"] = 10
data["b"] = old_data
storage, form = get_form(data)
print(storage, form); print()
