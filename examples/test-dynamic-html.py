import seamless
from seamless import context, cell, editor, transformer
from seamless.lib.filelink import link
from seamless.lib.gui.browser import browse

from seamless.websocketserver import websocketserver
websocketserver.start()

ctx = context()

import jinja2
tmpl = open("test-dynamic-html.jinja").read()
vars_ = ["bird"]
body = jinja2.Template(tmpl).render({"vars": vars_})

tmpl = """
<!DOCTYPE html>
<html>
<head></head>
<body>
<div id="echo"></div>
<div id="MyDiv"></div>
<div id="MyDiv2"></div>
{{body}}
</body>
</html>
"""
html_tmpl = jinja2.Template(tmpl).render({"body": body})
identifier = "test-dynamic-html"
html = jinja2.Template(html_tmpl).render({"IDENTIFIER": identifier, "socket": websocketserver.socket})

open("test.html", "w").write(html)
ctx.html = cell(("text", "html")).set(html)
browse(ctx.html)

msg = {"type":"html", "id": "MyDiv", "value": "Kakapo"}
websocketserver.send_message(identifier, msg)

msg = {"type":"var", "var": "bird", "value": "KAKAPO"}
websocketserver.send_message(identifier, msg)

js =  """
var ele = document.getElementById("MyDiv2");
ele.innerHTML = bird;
"""
msg = {"type":"eval", "value": js}
websocketserver.send_message(identifier, msg)


if not seamless.ipython:
    seamless.mainloop()
