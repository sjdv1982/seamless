import seamless
seamless.fair.add_server("https://fair.rpbs.univ-paris-diderot.fr")
seamless.delegate(level=1)
seamless.config.add_buffer_server("https://buffer.rpbs.univ-paris-diderot.fr")

from seamless.workflow import Context, Cell, DeepCell
ctx = Context()

ctx.pdb = DeepCell()

# Weakly reproducible way
distribution = DeepCell.find_distribution("pdb", date="2022-02-18", format="mmcif")
ctx.pdb.define(distribution)

# Strongly reproducible way
distribution = {
    "checksum": "eb377cf319b5dfa7651f41a09644c0d68934f8a8369998fdd82f003cfd5448f2",
    "keyorder": "3da0581cafcfb4b044419262474d6415317ff5863f7541ea0020ef7664cbfb85",
}
ctx.pdb.define(distribution)
ctx.compute()

print(ctx.pdb.status)
print(ctx.pdb.exception)
print(ctx.pdb.checksum)
print(ctx.pdb.keyorder_checksum)
print()
graph = ctx.save_graph("deepcell-pdb.seamless")

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
ctx.pdb_code = Cell("str").set("1brs")
ctx.pdb_structure = Cell("text").mount("/tmp/pdb_structure.mmcif", "w")
ctx.select_pdb = ctx.lib.select(
    celltype="text",
    input=ctx.pdb,
    selected=ctx.pdb_code,
    output=ctx.pdb_structure,
)
ctx.compute()
