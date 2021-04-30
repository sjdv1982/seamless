from seamless.highlevel import Context, Transformer, Cell
from seamless.stdlib import stdlib
import json

import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.system("rm -rf web")
os.system("mkdir web")
os.system("cp -r webcomponents web/components")

graph = json.load(open("../status-visualization.seamless"))

ctx = Context()
ctx.add_zip("../status-visualization.zip")
ctx.set_graph(graph)
ctx.gen_vis_status.code.mount("web/gen_vis_status")

ctx.include(stdlib.merge)
ctx.seamless2webform = Cell("code")
ctx.seamless2webform = open("seamless2webform.py").read()
ctx.seamless2webform.mount("web/seamless2webform.py")
ctx.gen_webform = Transformer()
ctx.gen_webform.graph = ctx.graph
ctx.gen_webform.pins.graph.celltype = "plain"
ctx.gen_webform.code = ctx.seamless2webform
ctx.initial_webform = ctx.gen_webform
ctx.initial_webform.celltype = "plain"
ctx.initial_webform.mount("web/initial-webform.json", "w")
ctx.initial_webform0 = Cell("text")
ctx.initial_webform0 = ctx.initial_webform
ctx.compute()

ctx.webform = Cell("plain").mount("web/webform.json")
ctx.webform0 = Cell("text")
ctx.link(ctx.webform, ctx.webform0)
ctx.webform_CONFLICT = Cell("text").mount("web/webform-CONFLICT.txt")
ctx.webform_STATE = Cell("str")
ctx.webform_DUMMY = Cell("text")
ctx.compute()

ctx.merge_webform = ctx.lib.merge(
    upstream=ctx.initial_webform0,
    modified=ctx.webform0,
    conflict=ctx.webform_CONFLICT,
    merged=ctx.webform_DUMMY,
    state=ctx.webform_STATE
)

ctx.webcomponents = Cell("plain").mount("web/components", as_directory=True)

ctx.generate_webpage = Transformer()
ctx.generate_webpage.code = open("generate-webpage.py").read()
ctx.generate_webpage.code.mount("web/generate-webpage.py")
ctx.generate_webpage.webform = ctx.webform
ctx.generate_webpage.pins.webform.celltype = "plain"
ctx.generate_webpage.components = ctx.webcomponents
ctx.generate_webpage.pins.components.celltype = "plain"
ctx.generate_webpage.seed = 0

ctx.webpage = ctx.generate_webpage

ctx.html.share("status.html")
ctx.index_html = Cell("text")
ctx.index_html.mimetype = "text/html"
ctx.index_html.share("index.html", toplevel=True)
ctx.index_html.mount("web/index.html", mode="rw")

ctx.index_js = Cell("text")
ctx.index_js.mimetype = "text/javascript"
ctx.index_js.share("index.js", toplevel=True)
ctx.index_js.mount("web/index.js", mode="rw")

ctx.index_html_INITIAL = ctx.webpage["index.html"]
ctx.index_html_INITIAL.celltype = "text"
ctx.index_html_CONFLICT = Cell("text").mount("web/index-CONFLICT.html")
ctx.index_html_STATE = Cell("str")
ctx.index_html_DUMMY = Cell("text")

ctx.merge_index_html = ctx.lib.merge(
    upstream=ctx.index_html_INITIAL,
    modified=ctx.index_html,
    conflict=ctx.index_html_CONFLICT,
    merged=ctx.index_html_DUMMY,
    state=ctx.index_html_STATE
)

ctx.index_js_INITIAL = ctx.webpage["index.js"]
ctx.index_js_INITIAL.celltype = "text"
ctx.index_js_CONFLICT = Cell("text").mount("web/index-CONFLICT.js")
ctx.index_js_STATE = Cell("str")
ctx.index_js_DUMMY = Cell("text")

ctx.merge_index_js = ctx.lib.merge(
    upstream=ctx.index_js_INITIAL,
    modified=ctx.index_js,
    conflict=ctx.index_js_CONFLICT,
    merged=ctx.index_js_DUMMY,
    state=ctx.index_js_STATE
)

ctx.js.share("seamless-client.js", toplevel=True)

ctx.compute()
ctx.save_graph("../webgen.seamless")
ctx.save_zip("../webgen.zip")
os.system("rm -rf web")