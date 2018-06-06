import sys
from seamless.silk import Silk, ValidationError

def adder(self, other):
    return other + self.x

s = Silk()
s.__add__ = adder
s.bla = adder
s.x = 80
print(s.x)
print(s.bla(5))
print(s+5)

s2 = Silk(s.schema.dict)
s2.x = 10
print(s2+5)

s3 = Silk(s2.schema.dict)
s3.x = 10
print(s3+25)

def xy(self):
    return self.x + self.y

s.x = 1
s.y = 2
s.xy = property(xy)
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
print(s.x)

s.z = {}
s.z.q = 12
s.z.r = 24
sz = s.z
print(sz.q, sz.r)
s.z.r = 25
print(sz.q, sz.r)
s.z.qr = property(lambda self: self.q * self.r)
print(s.z.qr)

def validate_z(self):
    print("VALIDATE", self.q, self.r)
    assert self.q < self.r
try:
    s.z.add_validator(validate_z)
except:
    print(s.schema)

print(s.schema)

s.lis = [1,2,3]
s.lis.append(10)
print(s.lis)
s.lis += [5]
print(s.lis*2)
for a in s.lis[1:3]:
    print(a)
print(hasattr(s, "lis"), "lis" in s)
print(hasattr(s, "lis2"), "lis2" in s)

for v in s:
    print(v)
print("")
for v in s.lis:
    print(v)

s = Silk().set(5)
inc = lambda self: self + 1
s.x = inc
print(s.x())
s.y = property(inc)
print(s.y)
def setter(self,v):
    self.data = v - 1
s.z = property(inc, setter)
print(s.z)
s.z = 10
print(s.data)
print(s.z)

import numpy as np
arr = np.array([1.0,2.0,3.0])
s2.arr = arr
print(s2.arr, arr)
print(type(s2.arr), type(arr))
print(s2.arr[2], arr[2])
print(type(s2.arr[2]), type(arr[2]))

#s2.arr.schema.type = "array"  #  inferred
item = Silk().set(5.0)
#item.schema.type = "number"  #  inferred
def func(self):
    assert self > 0
item.add_validator(func)
s2.arr.schema.items = item.schema
s2.validate()

s2.arr[0] = 5
print(s2.arr)

s = Silk()
s.x = 1.0
s.y = 0.0
s.z = 0.0
def func(self):
    assert abs(self.x**2+self.y**2+self.z**2 - 1) < 0.001
s.add_validator(func)
# s.y = 1.0   #  would fail
try:
    with s.fork():
        s.x = 0.0
        s.y = 0.0
        s.z = 1.0
        try:
            with s.fork():
                s.x = 0.0
                s.y = 1.0
                s.z = 0.0
                #s.y = 2.0 # restores to [0,0,1]
        except ValidationError:
            pass
        #s.z = 2.0 # restores to [1,0,0]
except ValidationError:
    pass
print(s)

import numpy as np
a = Silk()
a.coor = [0,0,1]
print(a.coor)
print("START")
np.array(a.coor)
print(np.array(a.coor))
def func(self):
    import numpy as np
    arr = np.array(self)
    assert abs(np.sum(arr**2) - 1) < 0.01
a.coor.add_validator(func)

c = Silk()
c.set( [0.0, 0.0, 0.0] )
c.schema = a.coor.schema
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
    with self.fork():
        self.x = x
        self.y = y
        self.z = z
c.xyz = property(lambda self: tuple(self.data), set_xyz)

with c.fork():
    c.x = 0.2
    c.y = -0.3
    c.z = 0.93
print(c)
c.xyz = -1,0,0
print(c, c.xyz)
print(c.schema)

Test = Silk()
def __init__(self, a, b):
    self.a = a
    self.b = b
def __call__(self, c):
    return self.a + self.b + c
Test.__init__ = __init__
Test.__call__ = __call__
test = Test(7,8)
print(test)
print(test(5))
print(test.schema)

print("START")
test.l = []
l = test.l
l.append("bla")
l.append(10) #Error
