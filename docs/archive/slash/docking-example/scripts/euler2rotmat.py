import sys, os
from read_struc import read_struc
from math import sin, cos
import numpy as np

def euler2rotmat(phi,ssi,rot):
    cs=cos(ssi)
    cp=cos(phi)
    ss=sin(ssi)
    sp=sin(phi)
    cscp=cs*cp
    cssp=cs*sp
    sscp=ss*cp
    sssp=ss*sp
    crot=cos(rot)
    srot=sin(rot)

    r1 = crot * cscp + srot * sp
    r2 = srot * cscp - crot * sp
    r3 = sscp

    r4 = crot * cssp - srot * cp
    r5 = srot * cssp + crot * cp
    r6 = sssp

    r7 = -crot * ss
    r8 = -srot * ss
    r9 = cs
    return ((r1,r2,r3),(r4,r5,r6),(r7,r8,r9))

datfile = sys.argv[1]
header, strucs = read_struc(open(datfile))
strucs = list(strucs)

pivots = []
for h in header:
    if not h.startswith("#pivot"):
        h = h.rstrip()
        if h.startswith("#centered"): assert h.endswith(" false"), h
        continue
    assert not h.startswith("#pivot auto"), h
    hh = h.split()
    assert hh[1] == str(len(pivots)+1), h
    assert len(hh) == 5, h
    pivot = [float(v) for v in hh[2:5]]
    pivots.append(np.array(pivot))

results = []
for struc in strucs:
    result_struc = []
    for lnr, l in enumerate(struc[1]):
        ll = [float(v) for v in l.split()]
        assert len(ll) == 6 #no ensembles
        rotmat = euler2rotmat(*ll[:3])
        rotmat = np.array(rotmat)
        trans = np.array(ll[3:6])
        p = pivots[lnr]
        pp = (-p * rotmat).sum(axis=1) + p
        trans += pp
        result = np.eye(4)
        result[:3,:3] = rotmat
        result[:3,3] = trans
        result[3][3] = 1
        result_struc.append(result.tolist())
    results.append(result_struc)
import json
print(json.dumps(results, indent=2))
