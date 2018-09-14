from seamless.highlevel import Context
ctx = Context()
ctx.mount_graph("/tmp/seamless", persistent=True)
ctx.a = {}
ctx.a.b = 12
print(ctx.a.value, ctx.a.value.data, ctx.a.value.data.value)
print(type(ctx.a.value), type(ctx.a.value.data), type(ctx.a.value.data.value))
####ctx.a.b = "test" ###should give error
ctx.tf = lambda x,y: x + y
ctx.tf.x = ctx.a.b
ctx.c = 20
ctx.tf.y = ctx.c
ctx.d = ctx.tf
ctx.equilibrate()
print(ctx.d.value) #32
print(ctx.tf.inp.value)
print()

print("Stage 2")
ctx.f0 = 20
ctx.q = {}
ctx.q.c = ctx.c
ctx.q.d = ctx.d
ctx.q.f = ctx.f0
ctx.q.g = 50
ctx.equilibrate()
print(ctx.q.value) #{'g': 50, 'c': 20, 'f': 20, 'd': 32}

print("Stage 3")
ctx.c = 7
ctx.equilibrate()
print(ctx.q.value) #{'g': 50, 'c': 7, 'f': 20, 'd': 19}

print("Stage 4")
ctx.z = 100
def func(q,z):
    return q.c * q.f - q.g + q.d + 2 * z
ctx.tf2 = func
ctx.tf2.q = ctx.q
ctx.tf2.z = ctx.z
ctx.qq = ctx.tf2
ctx.equilibrate()
print(ctx.qq.value) #309

print("Stage 5")
ctx.z += 10
ctx.c = 8
ctx.a.irrelevant = "irrelevant"
ctx.a.b = -12
ctx.equilibrate()
print(ctx.q.value) #{'g': 50, 'c': 8, 'f': 20, 'd': -4}
print(ctx.qq.value) #326

print("Stage 6")
def validator(self):
    print("VALIDATE", self)
    assert self.g > self.c + self.f
    assert self.f > self.d
ctx.q.handle.add_validator(validator)

print("Stage 7")
ctx.a.b = 100
ctx.equilibrate()
print(ctx.q.value) #{'g': 50, 'c': 8, 'f': 20, 'd': -4}
print(ctx.q.handle) #{'g': 50, 'c': 8, 'f': 20, 'd': 108}
print(ctx.qq.value) #326

print("Stage 8")
ctx.a.b = 80
ctx.equilibrate()
print(ctx.q.value) #{'g': 50, 'c': 8, 'f': 20, 'd': -4}
print(ctx.q.handle) #{'g': 50, 'c': 8, 'f': 20, 'd': 88}
print(ctx.qq.value) #326

print("Stage 9")
ctx.a.b = 4
ctx.equilibrate()
print(ctx.q.value)  #{'g': 50, 'c': 8, 'f': 20, 'd': 12}
print(ctx.q.handle) #{'g': 50, 'c': 8, 'f': 20, 'd': 12}
print(ctx.qq.value) #342
