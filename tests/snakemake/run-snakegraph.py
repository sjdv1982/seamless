import seamless
from seamless.highlevel import Context
import json
import numpy as np

cache = seamless.RedisCache()

print("Load graph...")
graph = json.load(open("snakegraph.seamless"))
ctx = seamless.highlevel.load_graph(graph)
ctx.translate()

print("Bind files...")
files = [("data/genome.tgz", "b"),
        ("data/samples/A.fastq", "t"),
        ("data/samples/B.fastq", "t")
]
for file, mode in files:
    data = open(file, "r" + mode).read()
    if mode == "b":
        data = np.frombuffer(data, dtype=np.uint8)
    ctx.filesystem[file] = data

print("Equilibrate...")
ctx.compute()
print()

print("File system contents:")
print(ctx.filesystem.status)
print(ctx.filesystem.exception)
fs = ctx.filesystem.value.unsilk
assert fs is not None
def print_file(f):    
    v = str(fs[f])
    if len(v) > 80:
        v = v[:35] + "." * 10  + v[-35:]
    print(f, v)
    print()

for f in sorted(list(fs.keys())):
    print_file(f)

import os
if "calls/all.vcf" in fs:
    print("SUCCESS, calls/all.vcf created")
    os.system("mkdir -p calls")
    with open("calls/all.vcf", "w") as f:
        f.write(fs["calls/all.vcf"])
