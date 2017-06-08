from seamless import context, cell
from seamless.lib import edit, display, link
from seamless.slash import slash0

ctx = context()
ctx.attract = cell(("text", "code", "slash-0"))
ctx.link_attract = link(ctx.attract, ".", "attract.slash")
ctx.equilibrate()
ctx.slash = slash0(ctx.attract)
ctx.pdbA = cell("text")
ctx.pdbB = cell("text")
ctx.link_pdbA = link(ctx.pdbA, ".", "1AVXA.pdb")
ctx.link_pdbB = link(ctx.pdbB, ".", "1AVXB.pdb")
ctx.pdbA.connect(ctx.slash.pdbA)
ctx.pdbB.connect(ctx.slash.pdbB)
ctx.energies = cell("text")
ctx.slash.energies.connect(ctx.energies)
display(ctx.energies)
