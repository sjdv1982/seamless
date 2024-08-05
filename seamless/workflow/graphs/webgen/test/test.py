from seamless.workflow import Context, Cell, Transformer, FolderCell, load_graph
from seamless.highlevel import stdlib
import os

ctx = Context()
ctx.include(stdlib.merge)
ctx.initial_graph = Cell("plain").mount("initial-graph.seamless", "r")
ctx.gen_webform = Transformer()
ctx.gen_webform.code.mount("../generate-webform.py", "r")
ctx.gen_webform.graph = ctx.initial_graph
ctx.gen_webform.pins.graph.celltype = "plain"
ctx.initial_webform = ctx.gen_webform
ctx.initial_webform.celltype = "plain"
ctx.initial_webform.mount("initial-webform.json", "w")
ctx.initial_webform0 = Cell("text")
ctx.initial_webform0 = ctx.initial_webform
ctx.compute()

ctx.webform = Cell("plain").mount("webform.json")
ctx.webform0 = Cell("text")
ctx.link(ctx.webform, ctx.webform0)
ctx.webform_BASE = Cell("text").mount("webform-BASE.txt")
ctx.webform_CONFLICT = Cell("text").mount("webform-CONFLICT.txt")
ctx.webform_STATE = Cell("str")
ctx.webform_DUMMY = Cell("text")
ctx.compute()

ctx.merge_webform = ctx.lib.merge(
    upstream=ctx.initial_webform0,
    base=ctx.webform_BASE,
    modified=ctx.webform0,
    conflict=ctx.webform_CONFLICT,
    merged=ctx.webform_DUMMY,
    state=ctx.webform_STATE
)

ctx.webcomponents = FolderCell().mount("components", "r")

ctx.generate_webpage = Transformer()
ctx.generate_webpage.code.mount("../generate-webpage.py", "r")
ctx.generate_webpage.webform = ctx.webform
ctx.generate_webpage.pins.webform.celltype = "plain"
ctx.generate_webpage.components = ctx.webcomponents
ctx.generate_webpage.pins.components.celltype = "plain"
ctx.generate_webpage.seed = 0

ctx.webpage = ctx.generate_webpage

ctx.share_namespace = "status"

ctx.index_html = Cell("text")
ctx.index_html.mimetype = "text/html"
ctx.index_html.share("index.html", toplevel=True)
ctx.index_html.mount("index.html", mode="rw")

ctx.index_js = Cell("text")
ctx.index_js.mimetype = "text/javascript"
ctx.index_js.share("index.js", toplevel=True)
ctx.index_js.mount("index.js", mode="rw")

ctx.index_html_INITIAL = ctx.webpage["index.html"]
ctx.index_html_INITIAL.celltype = "text"
ctx.index_html_BASE = Cell("text").mount("index-BASE.html")
ctx.index_html_CONFLICT = Cell("text").mount("index-CONFLICT.html")
ctx.index_html_STATE = Cell("str")
ctx.index_html_DUMMY = Cell("text")

ctx.merge_index_html = ctx.lib.merge(
    upstream=ctx.index_html_INITIAL,
    base=ctx.index_html_BASE,
    modified=ctx.index_html,
    conflict=ctx.index_html_CONFLICT,
    merged=ctx.index_html_DUMMY,
    state=ctx.index_html_STATE
)

ctx.index_js_INITIAL = ctx.webpage["index.js"]
ctx.index_js_INITIAL.celltype = "text"
ctx.index_js_BASE = Cell("text").mount("index-BASE.js")
ctx.index_js_CONFLICT = Cell("text").mount("index-CONFLICT.js")
ctx.index_js_STATE = Cell("str")
ctx.index_js_DUMMY = Cell("text")

ctx.merge_index_js = ctx.lib.merge(
    upstream=ctx.index_js_INITIAL,
    base=ctx.index_js_BASE,
    modified=ctx.index_js,
    conflict=ctx.index_js_CONFLICT,
    merged=ctx.index_js_DUMMY,
    state=ctx.index_js_STATE
)

import seamless
seamless_dir = os.path.dirname(seamless.__file__)
seamless_client = open(seamless_dir + "/js/seamless-client.js").read()
ctx.seamless_js = Cell("text").set(seamless_client).share("seamless-client.js")
ctx.seamless_js.mimetype="text/javascript"
ctx.seamless_js.share("seamless-client.js", toplevel=True)
ctx.seamless_js.mount("seamless-client.js")

ctx.compute()

ctx_original = Context()
def reload(graph):
    ctx_original.add_zip("initial-graph.zip")
    ctx_original.set_graph(graph)
    #ctx_original.translate() # not allowed in Seamless traitlet
    import asyncio
    asyncio.ensure_future(ctx_original.translation(force=True))

reload(ctx.initial_graph.value)
ctx_original.compute()

t = ctx.initial_graph.traitlet()
t.observe(lambda change: reload(change["new"]))
ctx.compute()
