import numpy as np

atom_dtype = np.dtype([("position","float32", 3),
                      ("color","float32", 3),
                      ("radius", "float32")])
radii = {
    "C" : 1.70,
    "O" : 1.52,
    "N" : 1.55,
    "H" : 1.20,
    "P" : 1.80,
    "S" : 1.80,
}
colors = {
    "C" : [0.2, 1.0, 0.2],
    "O" : [1.0, 0.3, 0.3],
    "N" : [0.2, 0.2, 1.0],
    "H" : [0.9, 0.9, 0.9],
    "P" : [1.0, 0.5, 0.0],
    "S" : [0.9, 0.775, 0.25],
}


lines = open(filename).readlines()
atoms0 = []
for l in lines:
    ll = l.split()
    if ll[0] not in ("ATOM" , "HETATM"):
        continue
    atomname = l[12:16].strip()
    x = float(l[30:38])
    y = float(l[38:46])
    z = float(l[46:54])
    chain = l[21]
    resnr = int(l[22:26])
    resname = l[17:20].strip()
    element = atomname[0]
    atoms0.append( ((x,y,z),element) )

atoms = np.zeros(len(atoms0), dtype=atom_dtype)
atoms["position"] = np.array([a[0] for a in atoms0], dtype="float32")
for anr, a in enumerate(atoms0):
    _, element = a
    radius = radii.get(element, 1.8)
    atoms[anr]["radius"] = radius
    color = colors.get(element, [1,0,0])
    atoms[anr]["color"] = color
atoms["position"] -= np.mean(atoms["position"],axis=0)
p = atoms["position"]
min = np.abs(np.min(p,axis=0))
max = np.abs(np.max(p,axis=0))
bound = np.max(np.concatenate([min,max]))
bound /= 5.0 #scale to this
p /= bound
atoms["radius"] /= bound
return atoms
