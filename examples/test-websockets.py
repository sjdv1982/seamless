import seamless
from seamless import context, cell, editor, transformer
from seamless.lib.filelink import link
ctx = context()

ctx.server = editor({})
ctx.servercode = ctx.server.code_start.cell()
link(ctx.servercode, ".", "test-websockets_pycell.py")
#ctx.servercode.fromfile("test-websockets_pycell.py")
ctx.server.code_update.cell().set("")
ctx.server.code_stop.cell().set("""
server.close()
loop.run_until_complete(server.wait_closed())
""")

from seamless.lib.gui.browser import browse

ctx.client = cell(("text", "html"))
link(ctx.client, ".", "test-websockets_client.html")
browse(ctx.client)

ctx.client2 = cell(("text", "html"))
link(ctx.client2, ".", "test-websockets_client2.html")
browse(ctx.client2)

if not seamless.ipython:
    seamless.mainloop()
