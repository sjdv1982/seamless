from turtle import st
import seamless
from seamless.workflow import Context, Transformer, Cell
from silk.Silk import RichValue
import json, os
import numpy as np
from seamless.metalevel.bind_status_graph import bind_status_graph

print("Load graph...")
graph = json.load(open("snakegraph.seamless"))
ctx = seamless.highlevel.load_graph(graph)
ctx.add_zip("snakegraph.zip")
ctx.translate()

print("Load status visualization context (adapted from visualize-graph test)")

seamless_dir = os.path.dirname(seamless.__file__)
status_graph0 = seamless_dir + "/graphs/status-visualization"
status_graph_file, status_graph_zip = status_graph0 + ".seamless", status_graph0 + ".zip"

bind_status_graph(ctx, status_graph_file, zips=[status_graph_zip])

print("Setup binding of files")

def bind(file, mode):
    data = open(file, "r" + mode).read()
    if mode == "b":
        data = np.frombuffer(data, dtype=np.uint8)
    setattr(ctx.fs, file, data)

def list_files():
    print("Virtual file system contents:")
    for fs_cellname in ctx.fs.get_children("cell"):
        fs_cell = getattr(ctx.fs, fs_cellname)
        value = fs_cell.value
        value2 = RichValue(value, need_form=True)
        if value2.value is None:
            continue
        if value2.storage == "pure-plain":
            v = str(value2.value)
            if len(v) > 80:
                v = v[:35] + "." * 10  + v[-35:]
        else:
            v = "< Binary data, length %d >" % len(value)
        print(fs_cellname + ":", v)
        print()


print("""
*********************************************************************
*  Interactive setup complete.
*********************************************************************

- Open http://localhost:5813/status/index.html in the browser")
- Periodically enter the command "list_files()" to list the current files
- Enter the following commands:

  bind("data/genome.tgz", "b")
  bind("data/samples/A.fastq", "t")
  bind("data/samples/B.fastq", "t")

- "ctx.compute()" or "await ctx.computation()"
   will block until the workflow is complete
""")