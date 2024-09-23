import seamless

seamless.delegate(False)

from seamless.workflow import Context

ctx = Context()
ctx.a = {}
ctx.translate()
ctx.a.b = 12
ctx.compute()
print(ctx.a.value, ctx.a.value.data)
print(type(ctx.a.value), type(ctx.a.value.data))

ctx.a.example.b = 1.1
ctx.compute()
print(ctx.a.value, ctx.a.value.data, ctx.a.schema)

ctx.tf = lambda x, y: x + y
ctx.tf.x = ctx.a.b
ctx.c = 20
ctx.tf.y = ctx.c
ctx.d = ctx.tf
ctx.compute()
print(ctx.d.value)  # 32
print(ctx.tf.inp.value)
print()

print("Stage 2")
ctx.f0 = 20
ctx.q = {}
ctx.translate()
ctx.q.c = ctx.c
ctx.q.d = ctx.d
ctx.q.f = ctx.f0
ctx.q.g = 50
ctx.compute()
print(ctx.q.value)  # {'c': 20, 'd': 32, 'f': 20, 'g': 50}

print("Stage 3")
ctx.c = 7
ctx.compute()
print(ctx.q.value)  # {'c': 7, 'd': 19, 'f': 20, 'g': 50}

print("Stage 4")
ctx.z = 100


def func(q, z):
    return q.c * q.f - q.g + q.d + 2 * z


ctx.tf2 = func
ctx.tf2.q = ctx.q
ctx.tf2.q.celltype = "silk"
ctx.tf2.z = ctx.z
ctx.tf2.z.celltype = "silk"
ctx.qq = ctx.tf2
ctx.compute()
print(ctx.qq.value)  # 309

print("Stage 5")
ctx.z += 10
ctx.c = 8
ctx.a.irrelevant = "irrelevant"
ctx.a.b = -12
ctx.compute()
print(ctx.q.value)  # {'c': 8, 'd': -4, 'f': 20, 'g': 50}
print(ctx.qq.value)  # 326

print("Stage 6")


def validator(self):
    print("VALIDATE", self)
    assert self.g > self.c + self.f
    assert self.f > self.d


ctx.q.add_validator(validator, "validator")
ctx.compute()

print("Stage 7")
ctx.a.b = 100
ctx.compute()
print(ctx.q.value)  # None
print(ctx.qq.value)  # None
print(ctx.q.exception)

print("Stage 8")
ctx.a.b = 80
ctx.compute()
print(ctx.q.value)  # None
print(ctx.qq.value)  # None
print(ctx.q.exception)

print("Stage 9")
ctx.a.b = 4
ctx.compute()
print(ctx.q.value)  # {'c': 8, 'd': 12, 'f': 20, 'g': 50}
print(ctx.qq.value)  # 342
