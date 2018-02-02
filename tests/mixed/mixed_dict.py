import numpy as np
from seamless.mixed import MixedDict, mixed_dict

data = {}
d = mixed_dict(data)
d["a"] = 10
assert d.value is data
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
print(data, d.form)
print(d.storage, d["b"].storage, d["b"]["bb"].storage)
d["a"] = np.arange(10)
print(d.storage, d["a"].storage, d["b"].storage, d["b"]["bb"].storage)
print(d["a"].value, d["a"][3].value)

d["a"] = list(range(10))
print(d["a"].value, d["a"][3].value)
print(d.storage, d["a"].storage, d["b"].storage, d["b"]["bb"].storage)
