import seamless
seamless.delegate(False)

from seamless.highlevel import Context, Cell, Transformer

ctx = Context()
ctx.a = {}
ctx.translate()
ctx.a.x = 20
ctx.a.y = 88
def validate(self):
    print("VALIDATE", self)
    assert self.x > 0
ctx.a.schema.add_validator(validate, "validate")
ctx.a.x = -1
ctx.translate()
print(ctx.a.value)
print(ctx.a.buffered)  # rarely, the join task will complete already, but usually, this prints None
print(ctx.a.handle)
ctx.compute()
print(ctx.a.value)
print(ctx.a.buffered)
print(ctx.a.handle)
ctx.a.x = 2
ctx.a.handle.xx = property(lambda self: self.x + 10)
ctx.compute()
print(ctx.a.value)
print(ctx.a.value.x)
print(ctx.a.value.xx)
print()

ctx.a.z = 100
def setter(self, value):
    self.z = value
a = ctx.a.handle # this will synchronize with ctx.a.value after computation
a.zz = property(lambda self: self.z, setter)
print(a.zz)
a.zz = 200
print(a.z)
ctx.compute()
print(ctx.a.value.z, ctx.a.value.zz)
print()

ctx.a.q = 101
def setter(self, value):
    self.q = value
ctx.a.handle.qq = property(lambda self: self.q, setter)
ctx.a.handle.get_qx = lambda self: self.q + self.x
ctx.compute()
a = ctx.a.value
print(a.q, a.qq, a.get_qx())  # this works, because ctx.a.value gets the full schema
a.z = -a.z # will not update ctx.a.value, because a deep copy is created every time
a.qq = 201 # will not update ctx.a.value, because a deep copy is created every time
ctx.compute()
print(a.z, ctx.a.value.z)
print(a.qq, ctx.a.value.qq)
print()

ctx.b = ctx.a.b
a = ctx.a.handle
a.b = {}
a.b.c = 12
def setter(self, value):
    self.d = value
a.b.set_d = setter
a.b.set_d(80)
ctx.compute()
print(ctx.b.value)

print("START")
def mean(self):
    return sum(self)/len(self)

ctx.l = Cell("plain").set([10, 20, 32])
ctx.schema = Cell("plain")
ctx.dummy = Cell()
ctx.translate()
ctx.link(ctx.schema, ctx.dummy.schema)
h = ctx.dummy.handle
h.mean = mean
ctx.tf = lambda l: "Mean: %.3f" % l.mean()
ctx.tf.debug.direct_print = True
ctx.tf.l = ctx.l
ctx.tf.pins.l.celltype = "silk"
ctx.tf.l_SCHEMA = ctx.schema
ctx.result = ctx.tf.result
ctx.result.celltype = "str"
ctx.compute()
print(ctx.tf.exception)
print(ctx.result.value)
