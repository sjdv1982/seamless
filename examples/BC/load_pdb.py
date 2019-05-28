import Bio.PDB
from io import StringIO
import numpy as np
pdb_data = StringIO(pdb)
p = Bio.PDB.PDBParser()
struc = p.get_structure("pdb", pdb_data)
coors = []
for residue in struc.get_residues():
    for atom in residue.get_atoms():
        if atom.name == "CA":
            coors.append(atom.coord)
coors = np.stack(coors)
result = coors.astype(float)
