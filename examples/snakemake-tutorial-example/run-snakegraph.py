import seamless
from seamless.workflow import Context
from silk.Silk import RichValue
import json
import numpy as np

print("Load graph...")
graph = json.load(open("snakegraph.seamless"))
ctx = seamless.highlevel.load_graph(graph)
ctx.add_zip("snakegraph.zip")
ctx.translate()

print("Bind files...")
files = [("data/genome.tgz", "b"),
        ("data/samples/A.fastq", "t"),
        ("data/samples/B.fastq", "t")
]

def bind(file, mode):
    data = open(file, "r" + mode).read()
    if mode == "b":
        data = np.frombuffer(data, dtype=np.uint8)
    setattr(ctx.fs, file, data)

for file, mode in files:
    bind(file, mode)

print("Compute...")
ctx.compute()
print()

print("Virtual file system contents:")
finished = []
for fs_cellname in ctx.fs.get_children("cell"):
    fs_cell = getattr(ctx.fs, fs_cellname)
    value = fs_cell.value
    value2 = RichValue(value, need_form=True)
    if value2.value is None:
        continue
    finished.append(fs_cellname)
    if value2.storage == "pure-plain":
        v = str(value2.value)
        if len(v) > 80:
            v = v[:35] + "." * 10  + v[-35:]
    else:
        v = "< Binary data, length %d >" % len(value)
    print(fs_cellname + ":", v)
    print()

import os
if "calls/all.vcf" in finished:
    print("SUCCESS, calls/all.vcf created")
    os.system("mkdir -p calls")
    with open("calls/all.vcf", "w") as f:
        f.write(getattr(ctx.fs, "calls/all.vcf").value.unsilk)
else:
    print("FAILURE, calls/all.vcf not created")
