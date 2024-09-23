import seamless

seamless.fair.add_server("https://fair.rpbs.univ-paris-diderot.fr")
seamless.delegate(level=1)
seamless.config.add_buffer_server("https://buffer.rpbs.univ-paris-diderot.fr")

from seamless.workflow import Context, Cell, DeepFolderCell, FolderCell
import shutil

shutil.rmtree("/tmp/pdb_folder", ignore_errors=True)
ctx = Context()

ctx.pdb = DeepFolderCell()

# Weakly reproducible way
distribution = DeepFolderCell.find_distribution(
    "pdb", date="2022-03-21", format="mmcif_flatfilenames"
)
ctx.pdb.define(distribution)

# Strongly reproducible way
distribution = {
    "checksum": "2399c9b9ac30b6a96684485bba15e104f9cc52cbffc5f816a7e14bddedc718b4",
    "keyorder": "d01f82ba7353c5d1debd55b8f7d216a885790a3be52854c03f471158325ead2f",
}
ctx.pdb.define(distribution)
ctx.compute()

print(ctx.pdb.status)
print(ctx.pdb.exception)
print(ctx.pdb.checksum)
print(ctx.pdb.keyorder_checksum)
print()
graph = ctx.save_graph("deepfolder-pdb.seamless")

print("STAGE 2")
ctx.trypsin = Cell("text")
ctx.trypsin = ctx.pdb["1avx.cif"]
ctx.compute()
print(ctx.trypsin.checksum)
print(ctx.trypsin.exception)
print(ctx.trypsin.value[:200])
print()

print("STAGE 3")
ctx.epo = Cell("text")
ctx.epo = ctx.pdb["1eer.cif"]
ctx.compute()
print(ctx.epo.checksum)
print(ctx.epo.value[:200])
print()

print("STAGE 4")
ctx.pdb.whitelist = ["1wej.cif", "1brs.cif", "7cei.cif"]
ctx.pdb_folder = FolderCell()
ctx.pdb_folder = ctx.pdb
ctx.pdb_folder.mount("/tmp/pdb_folder", "w")
ctx.compute()
print()

print("STAGE 5")
from seamless.workflow import stdlib

ctx.include(stdlib.select)
ctx.pdb_code = Cell("str").set("2sni.cif")
ctx.pdb_structure = Cell("text").mount("/tmp/pdb_structure.mmcif", "w")
ctx.select_pdb = ctx.lib.select(
    celltype="text",
    input=ctx.pdb,
    selected=ctx.pdb_code,
    output=ctx.pdb_structure,
)
ctx.compute()
