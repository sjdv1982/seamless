#from seamless.silk import Silk
from silk import Silk

def adder(self, other):
    return other + self.x

s = Silk()
s.__add__ = adder
s.bla = adder
s.x = 80
print(s.x)
print(s.bla(5))
print(s+5)

s2 = Silk(s.schema)
s2.x = 10
print(s2+5)

s3 = Silk(s2.schema)
s3.x = 10
print(s3+25)

def xy(self):
    return self.x + self.y

s.x = 1
s.y = 2
s.xy = property(xy)

def xx_get(self):
    return self.x * self.x
def xx_set(self, xx):
    import math
    self.x = math.sqrt(xx)

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
#s.z.qr = property(lambda self: self.q * self.r) # TODO: does not work yet
def qr(self):
    return self.q * self.r
s.z.qr = property(qr)
print(s.z.qr)

def validate_z(self):
    print("VALIDATE", self.q, self.r)
    assert self.q < self.r
try:
    s.z.add_validator(validate_z)
except:
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

schema = s2.arr.schema
schema["type"] = "array"
item = Silk().set(5)
#item.schema["type"] = "integer"
def func(self):
    assert self > 0
item.add_validator(func)
schema["items"] = item.schema
print(schema)
s2.validate()
