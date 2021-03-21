import sys
from pprint import pprint
from silk import Silk, ValidationError

def adder(self, other):
    return other + self.x

s = Silk()
s.__add__ = adder
s.bla = adder
s.x = 80
print(s.x.data)
print(s.bla(5))
print(s+5)

s2 = Silk(schema=s.schema)
s2.x = 10
print(s2+5)

s3 = Silk(schema=s2.schema)
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
for a in s.lis[1:3]:
    print(a.data)
print(hasattr(s, "lis"), "lis" in s)
print(hasattr(s, "lis2"), "lis2" in s)

for v in s:
    print(s[v].data)
print("")
for v in s.lis:
    print(v.data)
print()

s = Silk().set(5)
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
item = Silk().set(5.0)
#item.schema["type"] = "number"  #  inferred
def func(self):
    assert self > 0
item.add_validator(func)
s2.arr.schema["items"] = item.schema
s2.x.validate(full=False)
print("ARR", s2.arr, type(s2.arr))
for nr, ele in enumerate(s2.arr):
    print("ELE", nr, ele, type(ele))
    ele.validate(full=False)
s2.x.validate(full=False)
s2.validate()

s2.arr[0] = 5
print(s2.arr.unsilk)

s = Silk()
s.x = 1.0
s.y = 0.0
s.z = 0.0
def func(self):
    assert abs(self.x**2+self.y**2+self.z**2 - 1) < 0.001
s.add_validator(func)
s.validate()
try:
    s.y = 1.0   #  would fail
    s.validate()
except ValidationError:
    s.y = 0

s.x = 0.0
s.y = 0.0
s.z = 1.0
s.validate()

s.x = 0.0
s.y = 1.0
s.z = 0.0
s.validate()

print(s.data)

import numpy as np
a = Silk()
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

c = Silk()
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
    self.x = x
    self.y = y
    self.z = z
    self.validate()
c.xyz = property(lambda self: tuple(self.data), set_xyz)

c.x = 0.2
try:
    c.validate()
except ValidationError as exc:
    print(exc)
c.y = -0.3
c.z = 0.93
c.validate()
print(c.data)
c.xyz = -1,0,0
print(c.data, c.xyz)
pprint(c.schema)

Test = Silk()
def __init__(self, a, b):
    self.a = a
    self.b = b
def __call__(self, c):
    return self.a + self.b + c
Test.__init__ = __init__
Test.__call__ = __call__
test = Test(7,8)
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