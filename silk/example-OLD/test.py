import json

from os import getcwd, path
pth = path.abspath(path.join(getcwd(), "../../../"))
import sys;sys.path.append(pth)

from seamless.silk.minischemas import _minischemas, register_minischema, make_baseclass, NumpyClass, NumpyMaskClass

schema_files = "coordinate.minischema.json", "axissystem.minischema.json"

for filepath in schema_files:
    with open(path.join(getcwd(), filepath)) as f:
        data = json.load(f)

    register_minischema(data)


import numpy as np
dtype = _minischemas["AxisSystem"]["dtype"]
dummy_array = np.zeros(shape=(1,), dtype=dtype)
axis_struct = dummy_array[0].view(np.recarray)
axis_struct.origin.x = 10
print(axis_struct)

CoordBaseClass = make_baseclass("Coordinate", _minischemas["Coordinate"])
NumpyCoord = type("npCoordinate", (CoordBaseClass, NumpyClass), {})
numpy_coord = NumpyCoord(None, dummy_array[0]["origin"])
print(dummy_array[0]["origin"])

print(numpy_coord.x)
numpy_coord.x = 20
print(numpy_coord.x)
print(dummy_array)


"""
c = make_baseclass("AxisSystem", _minischemas["AxisSystem"])
npc = type("npAxisSystem", (c,NumpyClass), {} )
npcc = npc(None, a[0])
print(npcc._props)
print(type(npcc))
npcc_o = npcc.origin
"""
