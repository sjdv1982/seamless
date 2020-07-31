import seamless
from seamless.highlevel import load_graph
import sys, json

infile, outfile = sys.argv[1:]
graph = json.load(open(infile))

seamless.database_sink.connect()
seamless.database_cache.connect()

ctx = load_graph(graph)
ctx.compute()
colored_graph = ctx.get_graph()
with open(outfile, "w") as f:
    json.dump(colored_graph, f, indent=2, sort_keys=True)