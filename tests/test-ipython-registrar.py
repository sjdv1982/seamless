from seamless import context, cell, pythoncell, reactor, transformer
from seamless.lib.filelink import link
from seamless.lib.gui.basic_display import display
from seamless.lib.gui.browser import browse
from seamless.lib.gui.basic_editor import edit

ctx = context()
reg = ctx.registrar.ipython
ctx.code =  cell(("text", "code", "ipython"))
link(ctx.code, ".", "cell-test-ipython-registrar.ipy")
reg.register(ctx.code)

tf = ctx.get_func_html = transformer({
    "outp": {"pin": "output", "dtype": ("text", "html")},
})
tf.code.cell().set("return func_html" )
reg.connect("func_html", tf )
browse(tf.outp.cell())

tf = ctx.run_func = transformer({
    "i": {"pin": "input", "dtype": "int"},
    "outp": {"pin": "output", "dtype": "float"},
})
reg.connect("func", tf )
tf.code.cell().set("""
import time
start = time.time()
result = func(i)
print("func(%d) executed in %s seconds" % (i, time.time()-start))
return result
""")
display(tf.outp.cell(), "outp")
edit(tf.i.cell().set(100), "i")
