import json
from seamless.silk.minischemas import _minischemas, register_minischema, make_baseclass, NumpyClass, NumpyMaskClass
f1 = json.load(open("silk/example/coordinate.minischema.json"))
f2 = json.load(open("silk/example/axissystem.minischema.json"))
register_minischema(f1)
register_minischema(f2)
import numpy as np
dtype = _minischemas["AxisSystem"]["dtype"]
print(dtype)
a = np.zeros(shape=(1,),dtype=dtype)
aa = a[0].view(np.recarray)
aa.origin.x = 10
print(aa)

c = make_baseclass("Coordinate", _minischemas["Coordinate"])
npc = type("npCoordinate", (c,NumpyClass), {} )
npcc = npc(None, a[0]["origin"])

print(npcc.x)
npcc.x = 20
print(npcc.x)
print(a)


"""
c = make_baseclass("AxisSystem", _minischemas["AxisSystem"])
npc = type("npAxisSystem", (c,NumpyClass), {} )
npcc = npc(None, a[0])
print(npcc._props)
print(type(npcc))
npcc_o = npcc.origin
"""
