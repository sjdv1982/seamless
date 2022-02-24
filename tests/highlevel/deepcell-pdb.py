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
print(ctx.pdb.status)
print(ctx.pdb.exception)
print(ctx.pdb.checksum)
print()

print("STAGE 2")
ctx.trypsin = Cell("mixed")
ctx.trypsin = ctx.pdb["1avx"]
ctx.compute()
print(ctx.trypsin.checksum)
print(ctx.trypsin.value[:200])
print()

print("STAGE 3")
ctx.epo = Cell("mixed")
ctx.epo = ctx.pdb["1eer"]
ctx.compute()
print(ctx.epo.checksum)
print(ctx.epo.value[:200])
