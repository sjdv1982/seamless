import numpy as np
from seamless.core import cell, context
from seamless.mixed import Monitor, CellBackend

ctx = context(toplevel=True)
ctx.cell = cell("mixed").mount("/tmp/cell.mixed")

PATHS = [("a",), ("b",), ("b", "bb"), ("m1",), ("m2",)]
manager = ctx._get_manager()
manager.register_cell_paths(ctx.cell, [], PATHS)

def build_mixed(data):
    backend = CellBackend(ctx.cell)
    monitor = Monitor(backend)
    monitor.set_path((), data)
    d = monitor.get_path()
    return d

d = build_mixed({})
print("START")
d["a"] = 10
print(d.value)
print(d.form)
print(d["a"].value)
print()

d["b"] = {"bb": 20}
print(d.value)
db = d["b"]
print(d["b"].value)
print(d["b"]["bb"].value)
d["b"]["bb"].set(50)
print(d["b"]["bb"].value)
print(d.value, d.form)
print(d.storage, d["b"].storage, d["b"]["bb"].storage)
d["a"] = np.arange(10)
print(d.storage, d["a"].storage, d["b"].storage, d["b"]["bb"].storage)
print(d["a"].value, d["a"][3].value)

d["a"] = list(range(10))
print(d["a"].value, d["a"][3].value)
print(d.storage, d["a"].storage, d["b"].storage, d["b"]["bb"].storage)

dt = np.dtype([("m1", int),("m2",int)],align=True)
d = build_mixed(np.zeros(1,dt)[0])
print(d.storage, d.form, d.value)
d["m1"] = 10
d["m2"] = 20
