'''
from seamless.silk import Silk

buf = {}
s = Silk(buffer=buf)
s.x = 20
s.y = 88
def validate(self):
    print("VALIDATE", self)
    assert self.x > 0
s.add_validator(validate)
s.x = -1
print(s)
print(s.data)
print(buf)
'''

from seamless.highlevel import Context

ctx = Context()
ctx.a = {}
ctx.a.x = 20
ctx.a.y = 88
def validate(self):
    print("VALIDATE", self)
    assert self.x > 0
ctx.a.handle.add_validator(validate)
ctx.a.x = -1
ctx.translate()
print("OK")
print(ctx.a._get_cell().value)
print(ctx.a._get_cell().handle)
