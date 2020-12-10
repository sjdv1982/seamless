import seamless
from seamless.highlevel import load_graph, Cell
import os, sys

initial_graphfile = sys.argv[1]
initial_zipfile = sys.argv[2]
output_graphfile = sys.argv[3]
output_zipfile = sys.argv[4]
ctx = load_graph(initial_graphfile, zip=initial_zipfile)

ctx.html = Cell("text").mount("index.html", authority="file").share("index.html")
ctx.html.mimetype="html"
ctx.js = Cell("text").mount("index.js", authority="file").share("index.js")
ctx.js.mimetype="js"

seamless_dir = os.path.dirname(seamless.__file__)
seamless_client = open(seamless_dir + "/js/seamless-client.js").read()

ctx.seamless_js = Cell("text").set(seamless_client).share("seamless-client.js")
ctx.seamless_js.mimetype="js"

ctx.compute()
ctx.save_graph(output_graphfile)
ctx.save_zip(output_zipfile)
