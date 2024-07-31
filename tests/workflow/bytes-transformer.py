import seamless
seamless.delegate(False)
from seamless.highlevel import Context, Cell

def func(a):
    print(type(a), a)
    return True

ctx = Context()

print("#1")
ctx.tf = func
ctx.tf.pins.a.celltype = "bytes"
ctx.tf.a = b'abc'
ctx.compute()
print(ctx.status)
print(ctx.tf.logs)
print("tf.inp:", ctx.tf.inp.value)
print()

print("#2")
del ctx.tf
ctx.compute()
ctx.tf = lambda q: None
ctx.tf.language = "bash"
ctx.tf.code = 'cat q > RESULT'
ctx.tf.pins.q.celltype = "bytes"
ctx.tf.q = b'This is an auth buffer'
ctx.compute()
print(ctx.status)
print(ctx.tf.logs)
print("tf.inp:", ctx.tf.inp.value)
print()

print("#3")
ctx.q = Cell("bytes").set(b'A dependent buffer')
ctx.tf.q = ctx.q
ctx.compute()
print(ctx.status)
print(ctx.tf.logs)
print("tf.inp:", ctx.tf.inp.value)
print()

print("#4")
ctx.tf.q = b'This is again an auth buffer'
ctx.compute()
print(ctx.status)
print(ctx.tf.logs)
print("tf.inp:", ctx.tf.inp.value)
print()

print("#5")
ctx.q2 = Cell("bytes").set(b'Another dependent buffer')
ctx.tf.q = ctx.q2
ctx.compute()
print(ctx.status)
print(ctx.tf.logs)
print("tf.inp:", ctx.tf.inp.value)
print()
