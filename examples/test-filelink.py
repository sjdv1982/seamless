from seamless import context, cell
from seamless.lib.filelink import link
from seamless.lib.gui.basic_editor import edit

import tempfile, shutil

ctx = context()

#tmpdir = tempfile.mkdtemp()
tmpdir = tempfile.gettempdir()

msg = "Edit {0}: directory {1}, file {2}"

ctx.number = cell("int").set(1)
file_number = "number.txt"
title_number = "Number"
ctx.fl_number = link(ctx.number, tmpdir, file_number)
ctx.ed_number = edit(ctx.number, title_number)
print(msg.format(title_number, tmpdir, file_number))

ctx.text = cell("text").set("Lorem ipsum")
file_text = "text.txt"
title_text = "Text"
ctx.fl_text = link(ctx.text, tmpdir, file_text)
ctx.ed_text = edit(ctx.text, title_text)
print(msg.format(title_text, tmpdir, file_text))


#shutil.rmtree(tmpdir) #TODO: make exit hook
