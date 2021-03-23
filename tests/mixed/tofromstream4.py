#string tests for mixed to/from file

import sys
import numpy as np
from silk.mixed.get_form import get_form
from silk.mixed.io import to_stream, from_stream

import json

arr = np.zeros(10)

dt = np.dtype([
    ("a", np.uint32),
    ("b", np.float32),
    ("str1", "S4"),
    ("str2", "S5"),
], align=True)
arr2 = np.zeros(2, dtype=dt)
data = {"arr":  arr, "arr2": arr2, "v": arr2[0], "z": 10}
storage, form = get_form(data)

stream = to_stream(data, storage, form)
newdata = from_stream(stream, storage, form)
print(newdata["arr"].dtype == data["arr"].dtype)
print(newdata["arr"] == data["arr"])
print(newdata["arr"] == data["arr"])
print(newdata["arr2"]["str1"].tobytes() == data["arr2"]["str1"].tobytes())
print(newdata["arr2"]["str2"].tobytes() == data["arr2"]["str2"].tobytes())
print(newdata["arr2"].tobytes() == data["arr2"].tobytes())
print()
data = b'somebuffer'
storage, form = get_form(data)
stream = to_stream(data, storage, form)
newdata = from_stream(stream, storage, form)
print(data, newdata)
print(data == newdata)
