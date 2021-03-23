import sys
import numpy as np
from silk.mixed.get_form import get_form
from silk.mixed.io import to_stream, from_stream

import json

arr = np.zeros((10,2,6))
data = {"arr":  arr, "test": "test"}
storage, form = get_form(data)
print(form, storage); print()
print("stream")
stream = to_stream(data, storage, form)
newdata = from_stream(stream, storage, form)
print(newdata["arr"].tobytes() == data["arr"].tobytes())
print(newdata["test"] == data["test"])
