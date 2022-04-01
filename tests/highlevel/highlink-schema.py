from seamless.highlevel import Context, Cell
ctx = Context()

ctx.v = "test"
ctx.v_schema = Cell()
ctx.v_schema.celltype = "plain"
ctx.translate()
ctx.link(ctx.v.schema, ctx.v_schema)
ctx.translate()
ctx.v_schema.set({'type': 'integer'})
ctx.compute()
print(ctx.v.schema)
print("*" * 50)
print(ctx.v.exception)
print("*" * 50)
ctx.v.schema.set({})
ctx.compute()  # this is needed, else the 1.2 below might take effect first,
               # and then be overwritten by this. Seamless is async!!
print(ctx.v.schema)
print(ctx.v_schema.value)
ctx.v.example.set(1.2)
ctx.compute()
print("value:", ctx.v.value)
print("data:", ctx.v._data)
print("buffered:", ctx.v.buffered)
print(ctx.v_schema.value)
print("*" * 50)
print(ctx.v.exception)
print("*" * 50)
ctx.v_schema.set({"type": "string"})
ctx.compute()
print(ctx.v_schema.value)
print(ctx.v.schema)
print("value:", ctx.v.value)
