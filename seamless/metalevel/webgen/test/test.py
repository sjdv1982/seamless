from seamless.highlevel import Context, Cell, Transformer, Link
from seamless.stdlib import stdlib
import os

ctx = Context()
ctx.include(stdlib.merge)
ctx.initial_graph = Cell("plain").mount("initial-graph.seamless", "r")
ctx.seamless2webform = Cell("code").mount("../seamless2webform.py", "r")
ctx.gen_webform = Transformer()
ctx.gen_webform.graph = ctx.initial_graph
ctx.gen_webform.pins.graph.celltype = "plain"
ctx.gen_webform.code = ctx.seamless2webform
ctx.initial_webform = ctx.gen_webform
ctx.initial_webform.celltype = "plain"
ctx.initial_webform.mount("initial-webform.json", "w")
ctx.initial_webform0 = Cell("text")
ctx.initial_webform0 = ctx.initial_webform
ctx.compute()

ctx.webform = Cell("plain").mount("webform.json")
ctx.webform0 = Cell("text")
ctx.link(ctx.webform, ctx.webform0)
ctx.webform_CONFLICT = Cell("text").mount("webform-CONFLICT.txt")
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
ctx.compute()