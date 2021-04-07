# Identical to schema.py, except for the hash pattern
# (and should give the same output, except that there will be no AttributeError upon accessing a non-existent member)
import sys
from pprint import pprint
from silk import Silk, ValidationError
from seamless.core import context, cell, StructuredCell

ctx = None
hash_pattern = {"*": "#"}

def reset_backend(share_schemas=True, with_hash_pattern=True):
    hp = hash_pattern if with_hash_pattern else None
    global ctx, s, s2, s3
    if ctx is not None:
        ctx.compute() # makes no difference, but could be easier debugging
        ctx.destroy()
    ctx = context(toplevel=True)
    ctx.data = cell("mixed", hash_pattern=hp)
    ctx.buffer = cell("mixed", hash_pattern=hp)
    ctx.schema = cell("plain")
    ctx.sc = StructuredCell(
        buffer=ctx.buffer,
        data=ctx.data,
        schema=ctx.schema,
        hash_pattern=hp
    )
    s = ctx.sc.handle
    ctx.data2 = cell("mixed", hash_pattern=hp)
    ctx.buffer2 = cell("mixed", hash_pattern=hp)
    if share_schemas:
        schema2 = ctx.schema
    else:
        ctx.schema2 = cell("plain")
        schema2 = ctx.schema2
    ctx.sc2 = StructuredCell(
        buffer=ctx.buffer2,
        data=ctx.data2,
        schema=schema2,
        hash_pattern=hp
    )
    s2 = ctx.sc2.handle
    hp3 = None # never use hash pattern for this one
    ctx.data3 = cell("mixed", hash_pattern=hp3)
    ctx.buffer3 = cell("mixed", hash_pattern=hp3)
    if share_schemas:
        schema3 = ctx.schema
    else:
        ctx.schema3 = cell("plain")
        schema3 = ctx.schema3
    ctx.sc3 = StructuredCell(
        buffer=ctx.buffer3,
        data=ctx.data3,
        schema=schema3,
        hash_pattern=hp3
    )
    s3 = ctx.sc3.handle


reset_backend()

def adder(self, other):
    return other + self.x


s.x = 80
print(s.x.data)

ctx.compute()
pprint(ctx.buffer.value)
pprint(ctx.data.value)

s.__add__ = adder
s.bla = adder

pprint(s.data)
pprint(s.schema.value)

print(s.bla(5))
print(s+5)

ctx.compute()
print("OK")
pprint(ctx.buffer.value)
pprint(ctx.data.value)
pprint(ctx.schema.value)

s2.x = 10
print(s2+5, s2.bla(5))
ctx.compute()
print(ctx.data2.value)

s3.x = 10
print(s3+25)

def xy(self):
    return self.x + self.y

s.x = 1
s.y = 2
print(s.x + s.y)
s3.xy = property(xy) # all three Silks use the same schema
#pprint(s.schema.value)
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
ctx.compute()

def validate_z(self):
    print("VALIDATE", self.q.data, self.r.data)
    assert self.q < self.r

try:
    s.z.add_validator(validate_z)
except Exception:
    pprint(s.schema.value)

s.z.validate()
pprint(s.schema.value)

s.lis = [1,2,3]
s.lis.append(10)

ctx.compute()

print(s.lis.data)
s.lis += [5]
ctx.compute()
print(s.lis*2)

"""
for a in s.lis[1:3]:  # slices not yet supported by monitor
    print(a.data)
"""
for a in s.lis:
    print(a.data)
print(hasattr(s, "lis"), "lis" in s)
print(hasattr(s, "lis2"), "lis2" in s)

for v in sorted(s):
    #print(v.data)  # With Monitor, iteration does *not* give a Silk object
    print(v)

print("")
for v in s.lis:
    print(v.data)
print()

reset_backend(share_schemas=False, with_hash_pattern=False)
s2.x = 10
s.set(5)
inc = lambda self: self + 1
s.x = inc
ctx.compute()
print(s.x())
s.y = property(inc)
print(s.y)
ctx.compute()
def setter(self,v):
    self.set(v - 1)
s.z = property(inc, setter)
ctx.compute()
print(s.z)
s.z = 10
ctx.compute()
print(s.data)
print(s.z)
ctx.compute()

reset_backend(share_schemas=False)
s2.x = 10
import numpy as np
arr = np.array([1.0,2.0,3.0])
s2.arr = arr
ctx.compute()


# Need .self.data or .unsilk for Numpy arrays, because Numpy arrays have a .data method
print(s2.arr.self.data, arr)
print(s2.arr.unsilk, arr)
print(type(s2.arr.self.data), type(arr))
print(s2.arr[2].self.data, arr[2])
print(type(s2.arr[2].self.data), type(arr[2]))
ctx.compute()

#s2.arr.schema["type"] = "array"  #  inferred
print(s2.arr.schema["type"])
item = s3
item.set(5.0)
#item.schema["type"] = "number"  #  inferred
def func(self):
    assert self > 0
item.add_validator(func)
s2.arr.schema["items"] = item.schema
s2.validate()

print(s3.data)
print(s2.data)

ctx.compute()
print("START")
s2.arr[0] = 5
print(s2.arr.unsilk)

reset_backend()
s.x = 1.0
s.y = 0.0
s.z = 0.0
def func(self):
    assert abs(self.x**2+self.y**2+self.z**2 - 1) < 0.001
s.add_validator(func)
s.y = 0.0
s.validate()
ctx.compute()
try:
    s.y = 1.0   #  would fail
    ctx.compute() # to ensure that ctx.sc.exception is set
    s.validate()
except ValidationError:
    print("FAIL")
    print(ctx.sc.exception)
    s.y = 0
#pprint(s.schema.value)
ctx.compute()

#print("set")
s.x = 0.0
s.y = 0.0
s.z = 1.0
ctx.compute()
print(s.data)

s.x = 1.0
s.y = 0.0
s.z = 0.0
ctx.compute()
print(s.data)

import numpy as np
reset_backend(share_schemas=False)
a = s
a.coor = [0.0,0.0,1.0]
ctx.compute()
pprint(a.coor.schema.value)
print(a.coor.data)
print("START")
np.array(a.coor.data)
print(np.array(a.coor.data))
def func(self):
    import numpy as np #necessary!
    arr = np.array(self.data)
    assert abs(np.sum(arr**2) - 1) < 0.01
a.coor.add_validator(func)
ctx.compute()
coor_schema = a.coor.schema.value

reset_backend(share_schemas=False, with_hash_pattern=False)
c = s2
c.schema.clear()
ctx.compute()
c.set( [0.0, 0.0, 0.0] )
ctx.compute()
c.schema.update(coor_schema)
ctx.compute()

def set_x(self, value):
    self[0] = value
c.x = property(lambda self: self[0], set_x)
ctx.compute()

def set_y(self, value):
    self[1] = value
c.y = property(lambda self: self[1], set_y)
ctx.compute()

def set_z(self, value):
    self[2] = value
c.z = property(lambda self: self[2], set_z)
ctx.compute()

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
pprint(c.schema.value)
ctx.compute()

ctx.destroy()
ctx = context(toplevel=True)
ctx.data = cell("mixed")
ctx.buffer = cell("mixed")
ctx.schema = cell("plain")
ctx.sc = StructuredCell(
    buffer=ctx.buffer,
    data=ctx.data,
    schema=ctx.schema
)

Test = ctx.sc.handle # singleton
"""
# will never work for a singleton backed up by a structured cell
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
pprint(test.schema.value)
ctx.compute()

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
ctx.compute()
print(test.l.data)
