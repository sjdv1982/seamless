from jsonschema.exceptions import ValidationError
from silk import Silk

print("START #1")
s = Silk()
print(s.schema)
s.set("test")
print(s.data)
s.validate()
print(s.schema)
print()

print("START #2")
s = Silk().set(1)
s.validate()
s.set(2.0)
print(s.data)
try:
    s.validate() # error
except ValidationError as exc:
    print(exc)
print()

print("START #3")
s = Silk()
s.a = 1
s.validate()
s.a = 3.0
try:
    s.validate() # error
except ValidationError as exc:
    print(exc)
print(s.data)
print(s.schema)
print()

print("START #4")
s = Silk().set({})
s.b = 12
s.validate()
print(s.data)
s["b"] = "test string"
try:
    s.validate() # error
except ValidationError as exc:
    print(exc)
print()

print("START #5")
s = Silk().set( [] )
s.append(1)
s.append(2)
print("VALUE: ", s.data)
print(s.schema)
s.append(3.0)
try:
    s.validate() # error
except ValidationError as exc:
    print(exc)
print()

print("START #6")
s.pop(-1)
print("VALUE: ", s.data)
def v(self):
    assert self > 0
s.add_validator(v, attr=0)   #  add a validator to v[0] => to all items
s.append(10)
s.validate()
s.append(0)
try:
    s.validate() # error
except ValidationError as exc:
    print(exc)
