import seamless
from seamless import context, cell
ctx = context()
ctx.value = cell("int")
from seamless.lib.gui.combobox import combobox
ctx.combobox = combobox("int", [10, 20, 30])
from seamless.lib.filelink import link
link(ctx.combobox.code_start.cell())
link(ctx.combobox.code_update.cell())
ctx.combobox.value.connect(ctx.value)
