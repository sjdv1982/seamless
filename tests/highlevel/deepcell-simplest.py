from seamless.highlevel import Context
ctx = Context()
ctx.a = {"test": 1}
ctx.a.celltype = "mixed"
ctx.a.hash_pattern = {"*": "#"}
print(ctx.a._get_hcell())
ctx.compute()
print(ctx.a._get_cell().data)
print(ctx.a._get_cell().value)
print(ctx.a._get_cell()._hash_pattern)
print(ctx.a.data)
print(ctx.a.value)
print(ctx.a.value)
print(ctx.a.value["test"])
