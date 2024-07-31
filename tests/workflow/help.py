import seamless
seamless.delegate(False)

from seamless.highlevel import Context, Cell, Transformer

import inspect
def hhelp(obj):
    # Similar to doing obj? in IPython
    # Standard Python help() does not work with Python 3.8. Fixed in Python 3.9
    print("*" * 80)
    print(inspect.getdoc(obj))
    print("*" * 80)

print("###", 1)
ctx = Context()
ctx.help = "This is an example help"
hhelp(ctx)
print(ctx.help.value)
ctx.compute()
hhelp(ctx)
print(ctx.help.value)
print()

print("###", 2)
ctx.help.ctx.a = "A markdown doc to document the main ctx"
ctx.help.ctx.a.mimetype = "markdown"
ctx.help.ctx.b = "A HTML doc to document the main ctx"
ctx.help.ctx.b.mimetype = "html"
print(ctx.help.ctx.a.value)
print(ctx.help.ctx.b.value)
ctx.compute()
print(ctx.help.ctx.a.value)
print(ctx.help.ctx.b.value)
print()

print("###", 3)
ctx.help.mount("/tmp/help-example.txt", authority="cell", persistent=False)
ctx.help.ctx.a.mount("/tmp/help-a.md", authority="cell", persistent=False)
ctx.help.ctx.b.mount("/tmp/help-b.html", authority="cell", persistent=False)
ctx.compute()
print()

print("###", 4)
ctx.help.share("help-example.txt")
ctx.help.ctx.a.share("help-a.md")
ctx.help.ctx.b.share("help-b.html")
ctx.compute()
print()

print("###", 5)
ctx.subctx = Context()
ctx.subctx.help = "This is documentation for a subcontext"
ctx.subctx.help.ctx.doc1 = "More documentation for a subcontext"
ctx.mycell = 123
ctx.mycell.help = "This is documentation for my cell"
ctx.mycell.help.ctx.doc1 = "More documentation for my cell"
ctx.tf = Transformer()
ctx.tf.help = "This is documentation for my transformer"
ctx.tf.help.ctx.doc1 = "More documentation for my transformer"
ctx.compute()
print(ctx.subctx.help.value)
print(ctx.subctx.help.ctx.doc1.value)
print(ctx.mycell.help.value)
print(ctx.mycell.help.ctx.doc1.value)
print(ctx.tf.help.value)
print(ctx.tf.help.ctx.doc1.value)
print()

print("###", 6)
import numpy as np
from matplotlib import pyplot as plt
plt.scatter([0, 1, 2, 3], [12, 7, 5, 6])
from io import BytesIO
f = BytesIO()
plt.savefig(f)
png = f.getvalue()
ctx.help.ctx.pictures = Context()
pic1 = Cell(celltype="bytes")
ctx.help.ctx.pictures.pic1 = pic1 
ctx.help.ctx.pictures.pic1_txt = "Description of picture 1"
pic1.set(png)
pic1.mount("/tmp/pic1.png", authority="cell", persistent=False)
ctx.compute()
print()

print("###", 7)
ctx.help.ctx.pictures.pic1.share("help/pic1.png")
ctx.help.ctx.pictures.pic1.mimetype = "png"
ctx.help.ctx.pictures.pic1_html = """
<title>Picture 1</title>
<h3>Picture 1</h3>
<div>
<img src="./pic1.png"></img>
</div>
<div>
This is picture 1
</div>
"""
ctx.help.ctx.pictures.pic1_html.mimetype = "html"
ctx.help.ctx.pictures.pic1_html.share("help/pic1.html")
ctx.compute()
print()

print("###", 8)
def calc_help(help_language):
    if help_language == "English":
        return "Help in English"
    elif help_language == "French":
        return "Aide en Français"
ctx.calc_help = calc_help
ctx.calc_help.help_language = "English"
ctx.help.ctx.multi_lingual = Cell()
ctx.help.ctx.multi_lingual.mimetype = "html"
ctx.help.ctx.multi_lingual.connect_from(ctx.calc_help)
ctx.compute()
print(ctx.help.ctx.multi_lingual.value)
ctx.calc_help.help_language = "French"
ctx.compute()
print(ctx.help.ctx.multi_lingual.value)
ctx.help.ctx.multi_lingual.share("help/multi-lingual.html")
ctx.compute()