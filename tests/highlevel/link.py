from seamless.highlevel import Context, Cell, Link

ctx = Context()
ctx.tf = lambda a,b: 42
ctx.x = ctx.tf.code
ctx.y = ctx.x
ctx.z = ctx.y
ctx.translate()
print(ctx.tf.code.value)
print(ctx.x.value)
print(ctx.y.value)
print(ctx.z.value)

ctx.x = "blah"
print(ctx.x._get_hcell())
ctx.x.datatype = "text"
print(ctx.tf.code.value)
print(ctx.x.value)
print(ctx.y.value)
print(ctx.z.value)

ctx.tf.code = lambda q,r: 10
print(ctx.tf.code.value)
print(ctx.x.value)

ctx.z = ctx.tf.code
ctx.x = "blah2"
print(ctx.tf.code.value)
print(ctx.x.value)
print(ctx.y.value)
print(ctx.z.value)

ctx.tf_code2 = Cell()
ctx.tf_code2.datatype = "text"
ctx.link_tf = Link(ctx.tf_code2, ctx.tf.code)
print(ctx.tf.code.value)
print(ctx.tf.code.value, ctx.tf_code2.value)
ctx.tf_code2.set("q * r")
print(ctx.tf.code.value, ctx.tf_code2.value)
ctx.tf.code = "r * q"
print(ctx.tf.code.value, ctx.tf_code2.value)

ctx.tf3 = lambda a,b: 0
ctx.link_tf2 = Link(ctx.tf3.code, ctx.tf.code)
print(ctx.tf.code.value,  ctx.tf_code2.value, ctx.tf3.code.value)
ctx.tf.code = "'tf'"
print(ctx.tf.code.value,  ctx.tf_code2.value, ctx.tf3.code.value)
ctx.tf_code2 = "'tf2'"
print(ctx.tf.code.value,  ctx.tf_code2.value, ctx.tf3.code.value)
ctx.tf3.code = "'tf3'"
print(ctx.tf.code.value,  ctx.tf_code2.value, ctx.tf3.code.value)

print("*" * 100)
ctx.xx = Cell()
ctx.xx.datatype = "text"
ctx.translate()

ctx.link_x = Link(ctx.xx, ctx.x)
ctx.translate()
print(ctx.x.value)
print(ctx.xx.value)
print("modify x...")
ctx.x = "new x"
print(ctx.x.value)
print(ctx.xx.value)
print("modify xx...")
ctx.xx = "new xx"
print(ctx.x.value)
print(ctx.xx.value)

print("*" * 100)
ctx.xx2 = Cell()
ctx.xx2.celltype = "text"
ctx.link_x2 = Link(ctx.xx2, ctx.x)
ctx.translate()

print(ctx.x.value, ctx.xx.value, ctx.xx2.value)
print("modify x...")
ctx.x = "new x"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value)
print("modify xx...")
ctx.xx = "new xx"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value)
print("modify xx2...")
ctx.xx2 = "new xx2"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value)

print("*" * 100)
ctx.xx3 = Cell()
ctx.xx3.celltype = "text"
ctx.link_x3 = Link(ctx.xx2, ctx.xx3)
ctx.translate()

print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value)
print("modify x...")
ctx.x = "new x"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value)
print("modify xx...")
ctx.xx = "new xx"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value)
print("modify xx2...")
ctx.xx2 = "new xx2"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value)
print("modify xx3...")
ctx.xx3 = "new xx3"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value)

print("*" * 100)
ctx.xx4 = Cell()
ctx.xx4.celltype = "text"
ctx.link_x4 = Link(ctx.xx3, ctx.xx4)
ctx.translate()

print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value, ctx.xx4.value)
print("modify x...")
ctx.x = "new x"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value, ctx.xx4.value)
print("modify xx...")
ctx.xx = "new xx"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value, ctx.xx4.value)
print("modify xx2...")
ctx.xx2 = "new xx2"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value, ctx.xx4.value)
print("modify xx3...")
ctx.xx3 = "new xx3"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value, ctx.xx4.value)
print("modify xx4...")
ctx.xx4 = "new xx4"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value, ctx.xx4.value)

ctx.struc = {"a":1, "b":2, "c": 3}
ctx.struc2 = {}
print(ctx.struc.a)
ctx.link_struc = Link(ctx.struc.a, ctx.struc2.k)
print(ctx.struc.a, ctx.struc2.k)
ctx.struc.a = 999
print(ctx.struc.a, ctx.struc2.k)
ctx.struc2.k = 111
print(ctx.struc.a, ctx.struc2.k)
