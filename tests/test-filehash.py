from seamless import context, cell
from seamless.lib.filehash import filehash
from seamless.lib.gui.basic_display import display

import tempfile, os

ctx = context()

tmpdir = tempfile.gettempdir()

msg = "Edit {0}: directory {1}, file {2}"

ctx.text = cell("text").set("Lorem ipsum")
file_text = "text.txt"
title_text = "Text"
ctx.fh_text = filehash(tmpdir + os.sep + file_text)
ctx.d_text = display(ctx.fh_text.filehash.cell(), "Hash")
print(msg.format(title_text, tmpdir, file_text))

import os
ctx.tofile(os.path.splitext(__file__)[0] + ".seamless", backup=False)
