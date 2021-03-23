import sys
import numpy as np
from silk.mixed .get_form import get_form
import json

_print = print
def print(*args):
    for a in args:
        _print(json.dumps(a, indent=2, sort_keys=True), end=" ")
    _print()

storage, form = get_form(1)
print(storage, form); print()

storage, form = get_form("test")
print(storage, form); print()

storage, form = get_form(["test", "test2"])
print(storage, form); print()

storage, form = get_form([1, 10.0])
print(storage, form); print()

storage, form = get_form(["test", 1, True])
print(storage, form); print()

storage, form = get_form({
    "a": None,
    "b": False,
    "c": 10,
    "d": 20.0,
    "e": "OK",
    "f": [1,2],
})
print(storage, form); print()

storage, form = get_form(np.zeros(10, dtype=np.int32))
print(storage, form); print()

storage, form = get_form(np.zeros(20, dtype=np.bool))
print(storage, form); print()

dt = np.dtype([
    ("a", int),
    ("b", float),
], align=True)
storage, form = get_form(np.zeros(10, dtype=dt))
print(storage, form); print()
