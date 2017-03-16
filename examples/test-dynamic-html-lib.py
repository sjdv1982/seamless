import seamless
from seamless import context, cell, editor, transformer
from seamless.lib.filelink import link
from seamless.lib.gui.browser import browse
from seamless.lib.dynamic_html import dynamic_html
from seamless.lib.templateer import templateer

params = {
    "var_bird": {"type": "var",
                  "var": "bird",
                  "dtype": "str",
                  "evals":["eval_bird"]
                },
    "eval_bird": {"type": "eval"},
    "html_bird": {"type": "html", "id": "divbird2"},
}

ctx = context()

tmpl = """
<!DOCTYPE html>
<html>
<head></head>
<body>
<b>First bird:</b><br>
<div id="divbird">No bird</div>
<b>Second bird:</b><br>
<div id="divbird2">No bird either</div>
<br>
{{body}}
</body>
</html>
"""
ctx.html_tmpl = cell("text").set(tmpl)
ctx.templateer = templateer({"templates": ["html_tmpl"], "environment": {"body": ("text", "html")}})
ctx.html_tmpl.connect(ctx.templateer.html_tmpl)
ctx.dynamic_html = dynamic_html(params)
ctx.dynamic_html.dynamic_html.connect(ctx.templateer.body.cell())
ctx.dynamic_html.html_bird.cell().set("Kakapo")
ctx.dynamic_html.var_bird.cell().set("Owl")
js =  """
var ele = document.getElementById("divbird");
ele.innerHTML = bird;
"""
ctx.dynamic_html.eval_bird.cell().set(js)
browse(ctx.templateer.RESULT.cell())
