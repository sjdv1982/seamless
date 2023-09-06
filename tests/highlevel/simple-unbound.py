from seamless.highlevel import Context, Transformer
ctx = Context()
ctx.a = 123
def func(a):
    return a + 1000
tf = Transformer(func)
tf.a = 456
ctx.tf = tf
ctx.compute()
print(ctx.tf.result.value)

print()
print("tf2")
tf2 = Transformer(func)
tf2.a = ctx.a
ctx.tf2 = tf2
ctx.compute()
print(ctx.tf2.result.value)

ctx.a = 12
ctx.compute()
print(ctx.tf2.result.value)

tf2.a = 5
ctx.compute(0.1)
print(ctx.tf2.get_transformation_checksum())
tfm = tf2.get_transformation()
print(tfm.as_checksum())
tfm.compute()
print(tfm.value)
print(tfm.exception)
print(tfm.logs)
print(ctx.tf2.result.value)
print(ctx.tf2.logs)

print()
print("tf3")
tf3 = Transformer(func)
tf3.a = 99
tfm = tf3.get_transformation()
tfm.compute()
print(tfm.value)
print(tfm.exception)
print(tfm.logs)

print()
print("tf4")
tf4 = tf3.copy()
tf4.a = -9
tfm = tf4.get_transformation()
tfm.compute()
print(tfm.value)
print(tfm.exception)
print(tfm.logs)

print("verify transformation identities")
print()
cs = tfm.as_checksum()
ctx.tf4 = tf4
ctx.compute()
print(cs)
print(ctx.tf4.get_transformation_checksum())

