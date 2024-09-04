import seamless

seamless.delegate(False)

import json
from seamless import load_graph, Context

graph = json.load(open("twopi-result.seamless"))
zipfile = "twopi-result.zip"

""" # Does not work well...
ctx = load_graph(graph)
ctx.add_zip(zipfile)
ctx.translate(force=True)
print(ctx.pi.value)
"""

ctx = Context()
ctx.set_graph(graph)
ctx.add_zip(zipfile)
ctx.translate()
print(ctx.pi.value.unsilk)  # For now, None; could be defined immediately in future
print(ctx.twopi.value.unsilk)  # set to None, because of independence
ctx.compute()  # re-runs the computation;
# in the future, the graph will be loaded more smartly
# so that this is either not needed, or runs instantly (cache hit)
print(ctx.twopi.value.unsilk)
print()
