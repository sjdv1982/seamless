import seamless

seamless.delegate(False)

from seamless.workflow import Transformer, Cell, Context, Module

ctx = Context()
ctx.cython_module = Module()
ctx.cython_module.language = "ipython"
ctx.cython_code = Cell("code").mount("cell-cython.ipy")
ctx.cython_code.language = "ipython"
ctx.cython_module.code = ctx.cython_code

ctx.tf = Transformer()
ctx.tf.code = "cython_module.func(100)"
ctx.tf.cython_module = ctx.cython_module
ctx.compute()
print(ctx.tf.result.value)

ctx.vis = Transformer()
ctx.vis.code = "cython_module.func_html"
ctx.vis.cython_module = ctx.cython_module
ctx.html = ctx.vis
ctx.html.share("cython.html")
ctx.html.mimetype = "html"
ctx.compute()

print("Cython visualization can be seen at localhost:<REST PORT>/ctx/cython.html")
