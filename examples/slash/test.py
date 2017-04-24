code = """
@input_doc pdb
@input_var atom
@input_var nhead
@intern_json pdbsplit
@intern headatoms
#grep $atom !pdb | head $nhead > headatoms
#$ATTRACTTOOLS/splitmodel !pdb "model">NULL !> pdbsplit
~/attract/tools/splitmodel !pdb "model">NULL !> pdbsplit
@export pdbsplit
#@export headatoms
"""

from seamless import context, cell
from seamless.slash import slash0
ctx = context()
ctx.code = cell(("text", "code", "slash-0")).set(code)
ctx.slash0 = slash0(ctx.code)
