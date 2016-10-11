import json, sys
from pprint import pprint
from seamless.silk.typeparse.xmlschemaparse import xmlschemaparse, get_blocks, get_init_tree
from seamless.silk.registers.minischemas import _minischemas, register_minischema
from seamless.silk.registers.typenames import register, _silk_types
from seamless.silk.stringparse import stringparse

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

s = open("../example/coordinate.silkschema.xml").read()
schema_Coordinate = xmlschemaparse(s)
blocks_Coordinate = get_blocks(schema_Coordinate)["Coordinate"]
Coordinate = register(
    _minischemas["Coordinate"],
    validation_blocks=blocks_Coordinate["validationblocks"],
    error_blocks=blocks_Coordinate["errorblocks"],
    method_blocks=blocks_Coordinate["methodblocks"],
)
s = open("../example/vector.silkschema.xml").read()
schema_Vector = xmlschemaparse(s)
blocks_Vector = get_blocks(schema_Vector)["Vector"]
Vector = register(
    _minischemas["Vector"],
    validation_blocks=blocks_Vector["validationblocks"],
    error_blocks=blocks_Vector["errorblocks"],
)

s = open("../example/axissystem.silkschema.xml").read()
schema_AxisSystem = xmlschemaparse(s)
init_tree_AxisSystem = get_init_tree(schema_AxisSystem)["AxisSystem"]
AxisSystem = register(
    _minischemas["AxisSystem"],
    init_tree=init_tree_AxisSystem
)

cc = Coordinate(x=1, y=2, z=3)
cc = Coordinate(cc)
pprint(cc._data)
v = Vector(0.6,0.8,0)
pprint(v)

cc.make_numpy()
pprint(cc._data)
cc.z = 20
pprint(cc._data)

ax = AxisSystem((-1,-2,-3),cc,(4,5,6),(7,8,9))
ax = AxisSystem()
ax.x = cc
print(ax._data)
print(ax.origin._data)

axstr = str(ax)
print(axstr)

from seamless.silk.stringparse import stringparse
d = stringparse(axstr)
print(d, type(d))
d = stringparse(axstr, typeless=True)
print(d, type(d))
print(AxisSystem(d))

ax.make_numpy()
print(ax.json())
print(ax._data["origin"].data == ax.origin._data.data)
ax.origin._data[0] = 999
print(ax._data)

print(ax)
f4 = json.load(open("../example/test.minischema.json"))
minischema = register_minischema(f4)
Test = register(minischema, typename="Test")

classes = "Integer", "Float", "Bool", "String", "Coordinate", "AxisSystem", "Vector"
for c in classes:
    for arity in 1,2,3:
        cc = c + "Array" * arity
        globals()[cc] = _silk_types[cc]
c = CoordinateArray((1,2,3))
c.append((10,20,30))

z = IntegerArrayArrayArray(((1,2,3),(4,5,6)), ((10,20,30),(40,50,60)))

a0 = AxisSystemArray (AxisSystem((10,2,3)), AxisSystem((910,92,93)))
a1 = AxisSystemArray (AxisSystem((210,22,23)),)
a = AxisSystemArrayArray(a0,a1)

a.make_numpy()
ax = AxisSystem(z=(9,9,9))
a[1].append(ax)
a[1].pop(1)
t = Test(x=(1,2),y=("bla", False),q=(8,9,10))
ax.make_numpy()
t.ax = ax
t.make_numpy()
t.ax = None
t2 = t.copy()
#print(t2.numpy())
