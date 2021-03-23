#medium-complexity tests for mixed to/from file

import sys
import numpy as np
from silk.mixed.get_form import get_form
from silk.mixed.io import to_stream, from_stream

import json

arr = np.zeros(10)

dt = np.dtype([
    ("a", np.uint32),
    ("b", np.float32),
], align=True)
arr2 = np.zeros(2, dtype=dt)
data = {"arr":  arr, "arr2": arr2, "v": arr2[0], "z": 10}
storage, form = get_form(data)

embedded_data = data
dt0 = np.dtype([
    ("q", np.int32),
    ("r", np.int64),
], align=True)
dt = np.dtype([
    ("a", int),
    ("b", object),
    ("c", object),
    ("d", object),
    ("e", dt0),
], align=True)
data = np.zeros(1,dtype=dt)[0]
data["a"] = 10
data["b"] = embedded_data
data["c"] = [1,2,{"a":3, "b":4},5,[6,7]]
data["d"] = np.arange(-6, 0)

storage, form = get_form(data)
print(form, storage); print()
print("stream")
stream = to_stream(data, storage, form)
#print(stream)
newdata = from_stream(stream, storage, form)
print(newdata["a"] == data["a"])
print(newdata["b"]["arr"].tobytes() == data["b"]["arr"].tobytes())
print(newdata["b"]["arr2"].tobytes() == data["b"]["arr2"].tobytes())
print(newdata["b"]["v"].tobytes() == data["b"]["v"].tobytes())
print(newdata["b"]["z"] == data["b"]["z"])
print(newdata["c"] == data["c"])
print(newdata["d"].tobytes() == data["d"].tobytes())
print(newdata["e"] == data["e"])
print(newdata.dtype == data.dtype)
