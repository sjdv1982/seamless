import json, sys, os

from pprint import pprint
from seamless.silk.typeparse.xmlschemaparse import xmlschemaparse, get_blocks, get_init_tree
from seamless.silk.registers.minischemas import _minischemas, register_minischema
from seamless.silk.registers.typenames import register, _silk_types
from seamless.silk.stringparse import stringparse

f1 = json.load(open("example/coordinate.minischema.json"))
f2 = json.load(open("example/axissystem.minischema.json"))
f3 = json.load(open("example/vector.minischema.json"))
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

s = open("example/coordinate.silkschema.xml").read()
schema_Coordinate = xmlschemaparse(s)
blocks_Coordinate = get_blocks(schema_Coordinate)["Coordinate"]
Coordinate = register(
    _minischemas["Coordinate"],
    validation_blocks=blocks_Coordinate["validationblocks"],
    error_blocks=blocks_Coordinate["errorblocks"],
    method_blocks=blocks_Coordinate["methodblocks"],
)
s = open("example/vector.silkschema.xml").read()
schema_Vector = xmlschemaparse(s)
blocks_Vector = get_blocks(schema_Vector)["Vector"]
Vector = register(
    _minischemas["Vector"],
    validation_blocks=blocks_Vector["validationblocks"],
    error_blocks=blocks_Vector["errorblocks"],
)

s = open("example/axissystem.silkschema.xml").read()
schema_AxisSystem = xmlschemaparse(s)
init_tree_AxisSystem = get_init_tree(schema_AxisSystem)["AxisSystem"]
AxisSystem = register(
    _minischemas["AxisSystem"],
    init_tree=init_tree_AxisSystem
)

classes = "Integer", "Float", "Bool", "String", "Coordinate", "AxisSystem", "Vector"
for c in classes:
    for arity in 1,2,3:
        cc = c + "Array" * arity
        globals()[cc] = _silk_types[cc]

cc = Coordinate(x=1, y=2, z=3)
cc = Coordinate(cc)
pprint(cc._data)
v = Vector(0.6,0.8,0)
pprint(v)

cc.make_numpy()
pprint(cc._data)
cc.z = 20
pprint(cc._data)
cc0 = cc

cc = CoordinateArray((1,2,3),(4,5,6),(7,8,9))
cc.make_numpy()
print(cc)
cc.realloc(10)
print(cc)
print(cc.make_numpy())
cca = CoordinateArray.from_numpy(cc.make_numpy())
print(cca)
#cc.make_json()
ccc = CoordinateArrayArray(cc, [10*c for c in cc] + [(0,1,2)])
print(ccc)
CoordinateArrayArray(ccc)
ccc.make_numpy()
print(ccc, ccc._Len)
CoordinateArrayArray(ccc)

cc2 = CoordinateArray([-c for c in cc])
ccc2 = CoordinateArrayArray(cc2[:2], [10*c for c in cc2]+ [(0,-1,-2),(-12,-11,-10)], cc2[1:3])


#ccc.make_json()
CoordinateArrayArray(ccc)
print(ccc)
cccc = CoordinateArrayArrayArray(ccc,ccc2,ccc)
cccc[2][1][-1].z += 1000
print(cccc)
cccc2 = cccc.copy()
assert cccc2==cccc
print("START")
cccc.make_numpy()
print(cccc)
print(cccc2==cccc)
cccc3=CoordinateArrayArrayArray(cccc)
print(cccc3)
print(cccc2==cccc3)
print(cccc==cccc3)
cccc3.make_numpy()
print(cccc==cccc3)
cccc3.set(cccc)

print(cccc==cccc3)
print(cccc._Len, cccc._data.shape)
v2 = cccc2.pop(1)
v1 = cccc.pop(1)

print("START2")
print(cccc2==cccc)
print(v1==v2) #BUG:
print(cccc._Len, cccc._data.shape, v1._Len)
cccc.insert(1, v2)
cccc2.insert(1, v1)
print(cccc._Len, cccc._data.shape)
assert v2.storage == "json"
assert v1.storage == "numpy"
assert cccc[1].storage == "numpy"
assert cccc2[1].storage == "json"
assert cccc.storage == "numpy"
assert cccc2.storage == "json"
print(cccc2==cccc)
newshape = (10,5,7)
print(newshape)
cccc.realloc(newshape)
print(cccc._Len, cccc._data.shape)
print(cccc2==cccc)
print(cccc==cccc3)
print(cccc2==cccc3)

cc = cc0
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
ax.origin._data["x"] = 999
print(ax._data)

print(ax)
f4 = json.load(open("example/test.minischema.json"))
minischema = register_minischema(f4)
Test = register(minischema)
TestArray = _silk_types["TestArray"]
f5 = json.load(open("example/test2.minischema.json"))
minischema = register_minischema(f5)
Test2 = register(minischema, typename="Test2")

c = CoordinateArray((1,2,3))
c.append((10,20,30))

z = IntegerArrayArrayArray(((1,2,3),(4,5,6)), ((10,20,30),(40,50,60)))

a0 = AxisSystemArray (AxisSystem((10,2,3)), AxisSystem((910,92,93)))
a1 = AxisSystemArray (AxisSystem((210,22,23)),)
a = AxisSystemArrayArray(a0,a1)

a.make_numpy()
print(a._data.shape)
print(a[0]._data.shape, a[1]._data.shape)
ax = AxisSystem(z=(9,9,9))
print(len(a[1]), a[1]._data.shape)
a[1].append(ax)
ax2 = a[1].pop(1)
assert ax == ax2
t = Test(x=(1,2),y=("three", False),q=c)
t.ax = ax
#t.ax.make_numpy()
t.ax = None
t2 = t.copy()
print(t.numpy())
qq = t.q[0]
t.q.insert(0,qq*-20)
t.make_numpy()
t.ax=None
#test2=Test2(test=(t,))
ta = TestArray(t)
ta = TestArray(ta)
print('START')
test2=Test2(test=ta)
test2.make_numpy()
test3 = test2.copy("numpy")
print(test2.test[0])
#print(ta)
print(ta[0]==t)
print(ta[0].json())
print(t.json())
t.make_json()
print(ta[0]==t)

print('START2')

test2.make_json()
k=test2.test[0].copy()
k.x.a = -1
k.x.b = -2
test2.test.append(k)
#test2.make_numpy()
test2.test[0].make_numpy()
test2.test[1].make_numpy()
test2.test.make_numpy()

print(t)
print(test2)
print(test2._data["test"][1])
print(test2.test[1])
#k2 = test2.test.pop(1)
#print(k2._data)
#print(k2)
numpydata = test2.test[0].numpy()
Test.from_numpy(numpydata)
print("JSON")
test2ax = test2.test.copy("json")
print(test2ax)
print("NUMPY")
test2ax = test2.test.copy("numpy")
test2ax[1].ax = ((4,7,8),(2,2,2,),(6,2,0))
test2ax[1].q.realloc(20)
print( test2ax._data["LEN_q"], test2ax[1].q._Len)
test2ax[1].q.append((7,7,7))
print( test2ax._data["LEN_q"], test2ax[1].q._Len)
print(test2ax)
test2a = test2.copy("numpy")
print(test2a.test.storage, test2ax.storage)
test2a.test=test2ax
print(test2ax==test2a.test)
print(test2ax[1]==test2a.test[1])
