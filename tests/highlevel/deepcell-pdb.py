from seamless.highlevel import Context, Cell, DeepCell
ctx = Context()

ctx.pdb = DeepCell()
"""
# Trigger reproducibility warning
import seamless
seamless._defining_graph = True
import seamless; seamless._defining_graph = True
ctx.pdb.define("pdb")
del seamless._defining_graph
"""
ctx.pdb.define("pdb", date="2022-02-18")
ctx.compute()
ctx.trypsin = Cell("mixed")
ctx.trypsin = ctx.pdb["1avx"]
ctx.compute()
print(ctx.pdb.status)
print(ctx.pdb.exception)
print(ctx.pdb.checksum)
print(ctx.trypsin.checksum)
print(ctx.trypsin.value[:200])
