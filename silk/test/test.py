import json
from pprint import pprint
from seamless.silk.registers.minischemas import _minischemas, register_minischema
from seamless.silk.registers.typenames import register
f1 = json.load(open("../example/coordinate.minischema.json"))
f2 = json.load(open("../example/axissystem.minischema.json"))
f3 = json.load(open("../example/vector.minischema.json"))
register_minischema(f1)
register_minischema(f2)
register_minischema(f3)
import numpy as np
dtype = _minischemas["AxisSystem"]["dtype"]
print(dtype)
a = np.zeros(shape=(1,),dtype=dtype)
aa = a[0].view(np.recarray)
aa.origin.x = 10
print(aa)

Coordinate = register(_minischemas["Coordinate"])
Vector = register(_minischemas["Vector"])
AxisSystem = register(_minischemas["AxisSystem"])

cc = Coordinate(x=1,y=2,z=3)
cc = Coordinate(cc)
cc = Coordinate("1,2,3")
pprint(cc._data)
v = Vector(1,2,z=3)
pprint(v)

cc.make_numpy(aa.origin)
pprint(cc._data)
cc.z = 20
pprint(cc._data)

ax = AxisSystem((-1,-2,-3),cc,(4,5,6),(7,8,9))
print(ax._data)
print(ax.origin._data)
ax.make_numpy()
print(ax.dict())
print(ax._data["origin"].data == ax.origin._data.data)
ax.origin._data[0] = 999
print(ax._data)

f4 = json.load(open("../example/test.minischema.json"))
minischema = register_minischema(f4)
