code = """
@input_doc pdb
@input_var atom
@input_var nhead
@input_var res
@intern_json pdbsplit
@intern headatoms
@intern resatoms
grep $atom !pdb | head -$nhead > headatoms
grep $res !headatoms > resatoms
$ATTRACTTOOLS/splitmodel !pdb "model" >NULL !> pdbsplit
@export pdbsplit
@export headatoms
@export resatoms
"""

from seamless import context, cell
from seamless.slash import slash0
from seamless.lib.filelink import link
from seamless.lib.gui.basic_editor import edit

ctx = context()
ctx.code = cell(("text", "code", "slash-0")).set(code)
ctx.headatoms = cell("text")
ctx.resatoms = cell("text")

ctx.link_headatoms = link(ctx.headatoms, ".", "headatoms.pdb")
ctx.link_resatoms = link(ctx.resatoms, ".", "resatoms.pdb")
ctx.link_code = link(ctx.code, ".", "code.slash")

ctx.slash0 = slash0(ctx.code)
ctx.pdb = cell("text").fromfile("1AVXA.pdb")
ctx.pdb.connect(ctx.slash0.pdb)
ctx.pdbsplit = cell("json")
ctx.slash0.pdbsplit.connect(ctx.pdbsplit)
ctx.slash0.headatoms.connect(ctx.headatoms)
ctx.slash0.resatoms.connect(ctx.resatoms)


ctx.atom = cell("str").set("CA")
ctx.atom.connect(ctx.slash0.atom)
ctx.res = cell("str").set("GLN")
ctx.res.connect(ctx.slash0.res)
ctx.nhead = cell("str").set(100)
ctx.nhead.connect(ctx.slash0.nhead)

ctx.equilibrate()
