import seamless
from seamless.highlevel import Context
import json
import numpy as np

cache = seamless.RedisCache()

print("Load graph...")
graph = json.load(open("snakegraph.seamless"))
ctx = seamless.highlevel.load_graph(graph)

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
ctx.equilibrate()
import time; time.sleep(1) ## kludge
ctx.equilibrate()

print("File system contents:")
fs = ctx.filesystem.value.data.value
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
