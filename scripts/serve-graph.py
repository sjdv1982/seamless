# TODO: proper command line options (also for mounts)
import sys, json
from seamless.highlevel import load_graph
graph_file = sys.argv[1]
zipfile = sys.argv[2]
graph = json.load(open(graph_file))
ctx = load_graph(graph, mounts=False, shares=True)
ctx.add_zip(zipfile)
ctx.translate()