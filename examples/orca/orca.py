from seamless import context, cell, transformer, reactor
from seamless.lib.filelink import link
from seamless.lib.gui.basic_editor import edit
ctx = context()

#Register Silk data models for sideview point and fin point
ctx.silk_sideviewpoint = cell(("text", "code", "silk"))
ctx.silk_sideviewpoint.fromfile("sideviewpoint.silk")
ctx.registrar.silk.register(ctx.silk_sideviewpoint)
ctx.silk_fincircle = cell(("text", "code", "silk"))
ctx.silk_fincircle.fromfile("fincircle.silk")
ctx.registrar.silk.register(ctx.silk_fincircle)

ctx.points = cell("json")
ctx.link_points = link(ctx.points, ".", "sideview-points.json")

###############################################################
# Set up side view point editor
###############################################################
ctx.ed_sideview = reactor({
  "points": {
    "pin": "edit",
    "dtype": "json",
  }
})
#Do this first, to prevent a superfluous error message
ctx.registrar.silk.connect("SideviewPoint", ctx.ed_sideview)
ctx.registrar.silk.connect("SideviewPointArray", ctx.ed_sideview)

link(ctx.ed_sideview.code_start.cell(), ".", "cell-ed-sideview-start.py")
link(ctx.ed_sideview.code_update.cell(), ".", "cell-ed-sideview-update.py")
ctx.ed_sideview.code_stop.cell().set("widget.destroy()")
ctx.points.connect(ctx.ed_sideview.points)

###############################################################
# Set up viewer
# - provide the side points as circles
# - provide fincircles
###############################################################
ctx.view = reactor({
  "circles": {
    "pin": "input",
    "dtype": "json",
  },
  "fincircles": {
    "pin": "input",
    "dtype": "json",
  },
  "ellipsity": {
    "pin": "input",
    "dtype": "float",
  },
})
#Do this first, to prevent a superfluous error message
ctx.registrar.silk.connect("SideviewPoint", ctx.view)
ctx.registrar.silk.connect("SideviewPointArray", ctx.view)

#Do this first, to prevent a superfluous error message
ctx.registrar.silk.connect("FinCircle", ctx.view)
ctx.registrar.silk.connect("FinCircleArray", ctx.view)

link(ctx.view.code_start.cell(), ".", "cell-view-start.py")
link(ctx.view.code_update.cell(), ".", "cell-view-update.py")
ctx.view.code_stop.cell().set("""
if widget.painter is not None and widget.painter.isActive():
    widget.painter.end()
widget.destroy()
del timer
""")
ctx.points.connect(ctx.view.circles)

ctx.ellipsity = cell("float").set(1.15)
ctx.ellipsity.connect(ctx.view.ellipsity)
edit(ctx.ellipsity, "Ellipsity")

###############################################################
# Set up fincircle generator
###############################################################

ctx.fincircles = cell("json")
ctx.fincircles.connect(ctx.view.fincircles)
ctx.gen_fincircles = transformer({
    "fin_generators": {"pin": "input", "dtype": "json"},
    "fincircles": {"pin": "output", "dtype": "json"}
})

#Do this first, to prevent a superfluous error message
ctx.registrar.silk.connect("FinCircle", ctx.gen_fincircles)
ctx.registrar.silk.connect("FinCircleArray", ctx.gen_fincircles)
ctx.registrar.silk.connect("FinGenerator", ctx.gen_fincircles)
ctx.registrar.silk.connect("FinGeneratorArray", ctx.gen_fincircles)

link(ctx.gen_fincircles.code.cell(), ".", "cell-gen-fincircles.py")
ctx.fin_generator_data = cell("cson")
ctx.link_fin_generator_data = link(ctx.fin_generator_data, ".", "fingenerator.cson")
ctx.fin_generator_data.connect(ctx.gen_fincircles.fin_generators)

ctx.gen_fincircles.fincircles.connect(ctx.fincircles)
ctx.tofile("orca.seamless", backup=False)
