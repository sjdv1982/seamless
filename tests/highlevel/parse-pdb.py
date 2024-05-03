import seamless
err = seamless.delegate()
if err:
    print("Attempting without full delegation...")
    if seamless.delegate(level=3):
        exit(1)

from seamless.highlevel import Context

def count_atoms(pdbdata):
    from Bio.PDB import PDBParser
    parser = PDBParser()
    from io import StringIO
    d = StringIO(pdbdata)
    struc = parser.get_structure("pdb", d)
    return len(list(struc.get_atoms()))

ctx = Context()
ctx.pdbdata = open("1crn.pdb").read()
ctx.count_atoms = count_atoms
ctx.count_atoms.pdbdata = ctx.pdbdata
ctx.count_atoms.pins.pdbdata.celltype = "text"
ctx.count_atoms.environment.set_conda(
    open("parse-pdb-environment.yml").read(),
    "yaml"
)
ctx.compute()
print(ctx.count_atoms.status)
print(ctx.count_atoms.exception)
print(ctx.count_atoms.logs)
print()
print("Transformation checksum:")
print(ctx.count_atoms.get_transformation_checksum())