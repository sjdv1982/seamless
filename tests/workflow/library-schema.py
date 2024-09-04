import seamless

seamless.delegate(False)

from seamless.workflow import Context, Cell
from seamless.library import LibraryContainer
from silk.Silk import Silk

mylib = LibraryContainer("mylib")

constructor_schema = {}
example = Silk(schema=constructor_schema)


def mean(self):
    return (self.a + self.b) / 2


example.mean = mean


def validator(self):
    assert self.a > 0
    assert self.mean() > 0


example.add_validator(validator)


api_schema = {}
example = Silk(schema=api_schema)


def q(self):
    return 42


example.q = property(q)


def square(self):
    self.a = self.a * self.a


example.square = square


def constructor(ctx, libctx, a, b):
    print("a = {}".format(a))
    print("b = {}".format(b))
    ctx.a = a
    ctx.b = b


mylib.testlib = Context()

mylib.testlib.constructor = constructor
mylib.testlib.params = {
    "a": {"type": "value", "io": "input"},
    "b": {"type": "value", "io": "input"},
}
mylib.testlib.constructor_schema = constructor_schema
mylib.testlib.api_schema = api_schema

ctx = Context()
ctx.include(mylib.testlib)
ctx.inst = ctx.lib.testlib()
ctx.inst.a = 1000
ctx.inst.b = 2000
ctx.compute()

ctx.inst.a = -10
ctx.compute()
print(ctx.inst.exception)

ctx.inst.a = 10
ctx.inst.b = -1000
ctx.compute()
print(ctx.inst.exception)

ctx.inst.b = 200
ctx.compute()

print("START")
print(ctx.inst.q)
print(ctx.inst.a)
ctx.inst.square()
print(ctx.inst.a)
ctx.compute()
