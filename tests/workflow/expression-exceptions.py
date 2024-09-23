import seamless

seamless.delegate(False)

from seamless.workflow import Context, Cell

ctx = Context()
ctx.a = Cell()
ctx.a.celltype = "int"
ctx.compute()
ctx.a.set(1)
ctx.compute()
ctx.a.set("test")
ctx.compute()
print("*" * 80)
print(ctx.a.exception)
print(ctx.a.value)
print("*" * 80)

ctx.a = 12
ctx.compute()
ctx.a.celltype = "str"
ctx.b = ctx.a
ctx.b.celltype = "int"
ctx.compute()
print("*" * 80)
print("a", ctx.a.exception)
print("a", ctx.a.value)
print("*" * 80)
print("b", ctx.b.exception)
print("b", ctx.b.value)
print("*" * 80)

ctx.a = "test2"
ctx.compute()
print("*" * 80)
print("a", ctx.a.exception)
print("a", ctx.a.value)
print("*" * 80)
print("b", ctx.b.exception)
print("b", ctx.b.value)
print("*" * 80)

ctx.c = Cell()
ctx.c.celltype = "float"
ctx.translate()
ctx.c._get_cell().set_buffer(b"'blah'\n")
ctx.compute()
print("c", ctx.c.exception)
print(ctx.c.buffer)

print()
print("*" * 80)
print("* TRANSFORMER")
print("*" * 80)
print()
ctx.tf = lambda x, y: x + y
ctx.tf.pins.x.celltype = "int"
ctx.tf.pins.y.celltype = "int"
ctx.tf.x = 10
ctx.tf.y = 20
ctx.compute()
print(ctx.tf.result.value)
ctx.tf.x = "test"
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.status)
print()
print(ctx.tf.exception)
