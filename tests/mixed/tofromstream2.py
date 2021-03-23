import sys
import numpy as np
from silk.mixed.get_form import get_form
from silk.mixed.io import to_stream, from_stream

dt1 = np.dtype([
    ("a", int),
    ("b", int),
    ("c", ("float", 3)),
], align=True)

dt2 = np.dtype([
    ("a", int),
    ("b", int),
    ("c", object),
], align=True)

assert dt1.isalignedstruct
assert dt2.isalignedstruct
assert dt1["c"].subdtype

d1 = np.zeros(1, dt1)[0]
d2 = np.zeros(1, dt2)[0]
d2["c"] = np.zeros(3, float)

d1["a"] = d2["a"] = 10
d1["b"] = d2["b"] = 20
d1["c"][:] = d2["c"][:] = range(100,103)

storage1, form1 = get_form(d1)
storage2, form2 = get_form(d2)

print(storage1, form1)
print(storage2, form2)

stream1 = to_stream(d1, storage1, form1)
#print(stream1)
stream2 = to_stream(d2, storage2, form2)
#print(stream2)

newd1 = from_stream(stream1, storage1, form1)
print(newd1.tobytes() == d1.tobytes())
newd2 = from_stream(stream2, storage2, form2)
print(newd2["a"] == d2["a"])
print(newd2["b"] == d2["b"])
print(newd2["c"].tobytes() == d2["c"].tobytes())
