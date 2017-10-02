# Ugly piece of code to display a numpy array texture
try:
    ctx.display_numpy.destroy()
except AttributeError:
    pass
c = ctx.display_numpy = context()
c.title = cell("str").set("Numpy array")
c.aspect_layout = pythoncell().fromfile("AspectLayout.py")
c.registrar.python.register(c.aspect_layout)
c.display_numpy = reactor({
    "array": {"pin": "input", "dtype": "array"},
    "title": {"pin": "input", "dtype": "str"},
})
c.registrar.python.connect("AspectLayout", c.display_numpy)
c.title.connect(c.display_numpy.title)
c.display_numpy.code_update.set("update()")
c.display_numpy.code_stop.set("destroy()")
c.code = pythoncell()
c.code.connect(c.display_numpy.code_start)
c.code.fromfile("cell-display-numpy.py")
# /Ugly piece of code to display a texture
