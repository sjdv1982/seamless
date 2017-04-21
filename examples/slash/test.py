from seamless.slash import parse_slash0, ast_slash0_validate
example = """
@input_doc pdb
@input_var atom
@input_var nhead
@intern_json pdbsplit
@intern headatoms
grep $atom !pdb | head $nhead > headatoms
$ATTRACTTOOLS/splitmodel !pdb "model">NULL !> pdbsplit
@export pdbsplit
@export headatoms
"""
tree = parse_slash0(example)
ast_slash0_validate(tree)
#TODO: check assign once
