import numpy as np

pdb_lines = [l.split() for l in pdbindex.splitlines()]
pdb_names = [ll[0] for ll in pdb_lines]
pdb = np.array([(int(ll[1]), int(ll[2])) for ll in pdb_lines], np.uint32)
seg_lines = [l.split() for l in segindex.splitlines()]
seg = np.array([(int(ll[0]), int(ll[1]), int(ll[2])) for ll in seg_lines], np.uint32)
result = {
    "pdb_names": pdb_names,
    "pdb": pdb,
    "seg": seg,
}
