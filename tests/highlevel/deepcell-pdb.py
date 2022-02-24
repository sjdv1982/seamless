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
ctx.pdb.define("pdb", date="2022-02-18", format="mmcif")
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

print("STAGE 4")
from seamless.highlevel import stdlib
ctx.include(stdlib.select)
ctx.pdb_code = Cell("str").set("1avx")
ctx.pdb_structure = Cell("text").mount("/tmp/pdb_structure.mmcif", "w")
ctx.select_pdb = ctx.lib.select(
    celltype="text",
    input=ctx.pdb,
    selected=ctx.pdb_code,
    output=ctx.pdb_structure,
)
ctx.compute()
