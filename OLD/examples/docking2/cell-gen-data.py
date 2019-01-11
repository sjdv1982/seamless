import numpy as np
colors2 = colors.splitlines()
ene = [float(v) for v in energies.splitlines()]
ir = [float(v.split()[1]) for v in irmsds.splitlines()]
clust = [[int(vv) for vv in v.split()[3:]] for v in clusters.splitlines() ]
maxes = [len(ene), len(ir), max([max(c) for c in clust])]
nstruc = min(maxes)
result = []
for cnr, c in enumerate(clust):
    c = [v for v in c if v<= nstruc]
    x = [ir[v-1] for v in c]
    y = [ene[v-1] for v in c]
    colnr = cnr%len(colors2)
    result.append({"x":x, "y": y})
    result.append({
      "x": [np.mean(x)],
      "y": [np.mean(y)],
      "error_x": {"value": np.std(x), "type": "constant", "color": colors2[colnr]},
      "error_y": {"value": np.std(y), "type": "constant",  "color": colors2[colnr]},
     })

return result
