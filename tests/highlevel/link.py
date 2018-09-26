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

'''
ctx.tf_code2 = Cell()
ctx.link_tf = Link(ctx.tf_code2, ctx.tf.code)
'''

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
ctx.xx3 = "new xx3"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value)

print("*" * 100)
ctx.xx4 = Cell()
ctx.xx4.celltype = "text"
ctx.link_x4 = Link(ctx.xx3, ctx.xx4)
ctx.translate()

'''
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
ctx.xx3 = "new xx3"
print(ctx.x.value, ctx.xx.value, ctx.xx2.value, ctx.xx3.value)
'''
