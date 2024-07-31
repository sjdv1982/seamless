import seamless
seamless.delegate(False)

from seamless.workflow import Context, Cell
ctx = Context()

ctx.v = lambda a: 42
ctx.v.a = "test"
ctx.v_schema = Cell()
ctx.v_schema.celltype = "plain"
ctx.translate()
ctx.link(ctx.v.schema, ctx.v_schema)
ctx.translate()
ctx.v_schema.set({'type': 'object', 'properties': {'a': {'type': 'integer'}}})
ctx.compute()
print(ctx.v.schema)
print("*" * 50)
print(ctx.v.inp.exception)
print("*" * 50)
ctx.v.schema.set({})
ctx.compute()  # this is needed, else the 1.2 below might take effect first,
               # and then be overwritten by this. Seamless is async!!
print(ctx.v.schema)
print(ctx.v_schema.value)
ctx.v.inp.example.a = 1.2
ctx.compute()
print("value:", ctx.v.inp.value)
print("data:", ctx.v.inp.data)
print("buffered:", ctx.v.inp.buffered)
print(ctx.v_schema.value)
print("*" * 50)
print(ctx.v.inp.exception)
print("*" * 50)
ctx.v_schema.set({'type': 'object', 'properties': {'a': {'type': 'string'}}})
ctx.compute()
print(ctx.v_schema.value)
print(ctx.v.schema)
print("value:", ctx.v.inp.value)
print()

ctx.unlink(ctx.v.schema, ctx.v_schema)
ctx.link(ctx.v.result.schema, ctx.v_schema)
ctx.compute()
print("result value:", ctx.v.result.value)
print("result data:", ctx.v.result.data)
print("result buffered:", ctx.v.result.buffered)
print(ctx.v_schema.value)
print("*" * 50)
print(ctx.v.result.exception)
print("*" * 50)
ctx.v_schema.set({'type': 'integer'})
ctx.compute()
print(ctx.v.result.schema)
print(ctx.v_schema.value)
print(ctx.v.result.value)