import seamless
from seamless import context, cell, reactor, transformer
from seamless.lib.filelink import link
from seamless.lib.gui.browser import browse
import time

from seamless.websocketserver import websocketserver
websocketserver.start() #no-op if the websocketserver has already started

ctx = context()

import jinja2
tmpl = cell("text").fromlibfile(seamless.lib, "dynamic-html.jinja").value
vars_ = ["bird"]
body = jinja2.Template(tmpl).render({"vars": vars_})

tmpl = """
<!DOCTYPE html>
<html>
<head></head>
<body>
<b>First bird:</b><br>
<div id="divbird">No bird</div>
<b>Second bird:</b><br>
<div id="divbird2">No bird either</div>
<b>Last message received:<br></b>
<div id="echo"></div>
<br>
{{body}}
</body>
</html>
"""
html_tmpl = jinja2.Template(tmpl).render({"body": body})
identifier = "test-dynamic-html"
html = jinja2.Template(html_tmpl).render({"IDENTIFIER": identifier, "socket": websocketserver.socket})

open("test-dynamic-html.html", "w").write(html)
ctx.html = cell(("text", "html")).set(html)
browse(ctx.html)
seamless.run_work()

def send_echo_message(msg):
    import json
    echo_msg_value = "<pre>" + json.dumps(msg,indent=2) + "</pre"
    echo_msg = {"type":"html", "id": "echo", "value": echo_msg_value}
    websocketserver.send_message(identifier, echo_msg)

msg = {"type":"html", "id": "divbird2", "value": "Kakapo"}
websocketserver.send_message(identifier, msg)
send_echo_message(msg)

msg = {"type":"var", "var": "bird", "value": "Owl"}
websocketserver.send_message(identifier, msg)
#send_echo_message(msg)

js =  """
var ele = document.getElementById("divbird");
ele.innerHTML = bird;
"""
msg = {"type":"eval", "value": js}
websocketserver.send_message(identifier, msg)
#send_echo_message(msg)
