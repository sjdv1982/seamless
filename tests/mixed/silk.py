import sys
from pprint import pprint
from silk import Silk, ValidationError
from silk.mixed import Monitor, SilkBackend, MixedObject

def reset_backend(sb=None):
    if sb is None:
        sb = silk_backend
    sb._data = None
    sb._form = None
    sb._storage = None
    sb._silk = None

def adder(self, other):
    return other + self.x

silk_backend = SilkBackend()
monitor = Monitor(silk_backend)
mixed_object = MixedObject(monitor, ())

silk_backend2 = SilkBackend()
monitor2 = Monitor(silk_backend2)
mixed_object2 = MixedObject(monitor2, ())

silk_backend3 = SilkBackend()
monitor3 = Monitor(silk_backend3)
mixed_object3 = MixedObject(monitor3, ())

s = Silk(data=mixed_object)
silk_backend.set_silk(s)

s.x = 80
print(s.x.data)

s.__add__ = adder
s.bla = adder
print(s.bla(5))
print(s+5)

s2 = Silk(data=mixed_object2,schema=s.schema)
silk_backend2.set_silk(s2)
s2.x = 10
print(s2+5)

s3 = Silk(data=mixed_object3,schema=s2.schema)
silk_backend3.set_silk(s3)
s3.x = 10
print(s3+25)

def xy(self):
    return self.x + self.y

s.x = 1
s.y = 2
print(s.x + s.y)
s3.xy = property(xy) # all three Silks use the same schema
print(s.xy)


def xx_get(self):
    return self.x * self.x
def xx_set(self, xx):
    import math
    self.x = int(math.sqrt(xx))

s.x = 3
s.xx = property(xx_get, xx_set)
print(s.xx)
s.xx = 16
print(s.xx)
print(s.x.data)

s.z = {}
s.z.q = 12
s.z.r = 24
sz = s.z
print(sz.q.data, sz.r.data)
s.z.r = 25
print(sz.q.data, sz.r.data)
s.z.qr = property(lambda self: self.q * self.r)
print(s.z.qr)

def validate_z(self):
    print("VALIDATE", self.q.data, self.r.data)
    assert self.q < self.r
try:
    s.z.add_validator(validate_z)
except Exception:
    pprint(s.schema)

s.z.validate()
pprint(s.schema)

s.lis = [1,2,3]
s.lis.append(10)
s.validate()
print(s.lis.data)
s.lis += [5]
s.validate()
print(s.lis*2)
"""
for a in s.lis[1:3]:  # slices not yet supported by monitor
    print(a.data)
"""
for a in s.lis:
    print(a.data)
print(hasattr(s, "lis"), "lis" in s)
print(hasattr(s, "lis2"), "lis2" in s)

for v in s:
    #print(v.data)  # With Monitor, iteration does *not* give a Silk object
    print(v)
print("")
for v in s.lis:
    print(v.data)
print()

reset_backend()
s = Silk(data=mixed_object)
silk_backend.set_silk(s)
s.set(5)
inc = lambda self: self + 1
s.x = inc
print(s.x())
s.y = property(inc)
print(s.y)
def setter(self,v):
    self.set(v - 1)
s.z = property(inc, setter)
print(s.z)
s.z = 10
print(s.data)
print(s.z)

import numpy as np
arr = np.array([1.0,2.0,3.0])
s2.arr = arr
# Need .self.data or .unsilk for Numpy arrays, because Numpy arrays have a .data method
print(s2.arr.self.data, arr)
print(s2.arr.unsilk, arr)
print(type(s2.arr.self.data), type(arr))
print(s2.arr[2].self.data, arr[2])
print(type(s2.arr[2].self.data), type(arr[2]))

#s2.arr.schema["type"] = "array"  #  inferred
print(s2.arr.schema["type"])
reset_backend()
item = Silk(data=mixed_object)
silk_backend.set_silk(item)
item.set(5.0)
#item.schema["type"] = "number"  #  inferred
def func(self):
    assert self > 0
item.add_validator(func)
s2.arr.schema["items"] = item.schema
s2.validate()

print(silk_backend._data)
print(silk_backend2._data)

print("START")
s2.arr[0] = 5
print(s2.arr.unsilk)

reset_backend()
s = Silk(data=mixed_object)
silk_backend.set_silk(s)
s.x = 1.0
s.y = 0.0
s.z = 0.0
def func(self):
    assert abs(self.x**2+self.y**2+self.z**2 - 1) < 0.001
s.add_validator(func)
s.y = 0.0
s.validate()
try:
    s.y = 1.0   #  would fail
    s.validate()
except ValidationError:
    s.y = 0

# setting 3 inter-validated values at once is *really* inconvenient with SilkBackend...
try:
    s.x = 0.0
except ValidationError:
    pass
try:
    s.y = 0.0
except ValidationError:
    pass
s.z = 1.0

print(s.data)

try:
    s.x = 1.0
except ValidationError:
    pass
try:
    s.y = 0.0
except ValidationError:
    pass
s.z = 0.0


print(s.data)

import numpy as np
reset_backend()
a = Silk(data=mixed_object)
silk_backend.set_silk(a)
a.coor = [0.0,0.0,1.0]
pprint(a.coor.schema)
print(a.coor.data)
print("START")
np.array(a.coor.data)
print(np.array(a.coor.data))
def func(self):
    import numpy as np #necessary!
    arr = np.array(self.data)
    assert abs(np.sum(arr**2) - 1) < 0.01
a.coor.add_validator(func)

reset_backend(mixed_object2)
c = Silk(data=mixed_object2)
silk_backend2.set_silk(c)
c.set( [0.0, 0.0, 0.0] )
c.schema.clear()
c.schema.update(a.coor.schema)

def set_x(self, value):
    self[0] = value
c.x = property(lambda self: self[0], set_x)
def set_y(self, value):
    self[1] = value
c.y = property(lambda self: self[1], set_y)
def set_z(self, value):
    self[2] = value
c.z = property(lambda self: self[2], set_z)

def set_xyz(self, xyz):
    x,y,z = xyz
    try:
        self.x = x
    except ValidationError:
        pass
    try:
        self.y = y
    except ValidationError:
        pass
    self.z = z

c.xyz = property(lambda self: tuple(self.data), set_xyz)

try:
    c.x = 0.2
except ValidationError:
    pass
try:
    c.y = -0.3
except ValidationError:
    pass
c.z = 0.93
print(c.data)
c.xyz = -1,0,0
print(c.data, c.xyz)
c.xyz = 0.2,-0.3,0.93
print(c.data, c.xyz)
pprint(c.schema)

reset_backend()
Test = Silk(data=mixed_object) # singleton
silk_backend.set_silk(Test)

"""
# will never work for a singleton backed up by a mixed object
def __init__(self, a, b):
    self.a = a
    self.b = b
"""
def __call__(self, c):
    return self.a + self.b + c
#Test.__init__ = __init__
Test.__call__ = __call__
#test = Test(7,8)
test = Test
test.a, test.b = 7, 8
test.validate()
print(test.data)
print(test(5))
pprint(test.schema)

print("START")
test.l = []
l = test.l
l.append("bla")
test.validate()
try:
    l.append(10) #Error
    l.validate()
except ValidationError as exc:
    print(exc)
    l.pop(-1)
print(test.l.data)