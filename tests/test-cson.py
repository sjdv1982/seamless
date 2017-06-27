import seamless
from seamless import context, transformer, cell
from seamless.lib.filelink import link
ctx = context()
ctx.cson = cell("cson")
ctx.cson_link = link(ctx.cson, ".", "test-cson.cson")
ctx.json = cell("json")
ctx.json_link = link(ctx.json, ".", "test-cson.json")
tparams = {
    "inp": {"pin": "input", "dtype": "json"},
    "outp": {"pin": "output", "dtype": "json"}
}
ctx.tf = transformer(tparams)
ctx.cson.connect(ctx.tf.inp)
ctx.tf.outp.connect(ctx.json)
ctx.tf.code.cell().set("""
return inp
""")

import os
ctx.tofile(os.path.splitext(__file__)[0] + ".seamless", backup=False)

#if not seamless.ipython:
#    seamless.mainloop()
