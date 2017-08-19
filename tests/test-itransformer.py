from seamless import context
from seamless.lib.filelink import link
from seamless.lib.itransformer import itransformer
from seamless.lib.gui.basic_display import display
from seamless.lib.gui.browser import browse
from seamless.lib.gui.basic_editor import edit
ctx = context()
ctx.itf = itransformer({
    "i": {"pin": "input", "dtype": "int"},
    "outp": {"pin": "output", "dtype": "json"},
})
link(ctx.itf.code.cell(), ".", "cell-test-itransformer.ipy")
display(ctx.itf.outp.cell(), "outp")
edit(ctx.itf.i.cell().set(100), "i")
browse(ctx.itf.html.cell(), "Cython code")
