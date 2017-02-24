import seamless
from seamless import context, cell, editor, transformer
from seamless.lib.filelink import link
ctx = context()

ctx.server = editor({"socket": {"pin": "output", "dtype": "int"}})
ctx.servercode = ctx.server.code_start.cell()
link(ctx.servercode, ".", "test-websockets-lib_pycell.py")
#ctx.servercode.fromfile("test-websockets-lib_pycell.py")
ctx.server.code_update.cell().set("")
ctx.server.code_stop.cell().set("""server.close()""")

from seamless.lib.gui.browser import browse


ctx.client_template = cell("text")
link(ctx.client_template, ".", "test-websockets_client.jinja")

tf_params = {"inp":{"pin": "input", "dtype": "text"},
             "identifier":{"pin": "input", "dtype": "text"},
             "socket":{"pin": "input", "dtype": "int"},
             "outp":{"pin": "output", "dtype": ("text", "html")} }
tf_code = """
import jinja2
d = dict(IDENTIFIER=identifier, socket=socket)
return jinja2.Template(inp).render(d)
"""

ctx.client1 = cell(("text", "html"))
ctx.tf_client1 = transformer(tf_params)
ctx.server.socket.cell().connect(ctx.tf_client1.socket)
ctx.client_template.connect(ctx.tf_client1.inp)
ctx.tf_client1.code.cell().set(tf_code)
ctx.tf_client1.identifier.cell().set("First WebSocket client")
ctx.tf_client1.outp.connect(ctx.client1)
browse(ctx.client1)

ctx.client2 = cell(("text", "html"))
ctx.tf_client2 = transformer(tf_params)
ctx.server.socket.cell().connect(ctx.tf_client2.socket)
ctx.client_template.connect(ctx.tf_client2.inp)
ctx.tf_client2.code.cell().set(tf_code)
ctx.tf_client2.identifier.cell().set("Second WebSocket client")
ctx.tf_client2.outp.connect(ctx.client2)
browse(ctx.client2)

if not seamless.ipython:
    seamless.mainloop()
