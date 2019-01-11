ctx.array = cell("array")
ctx.title = cell("str").set("Numpy array")
ctx.aspect_layout = pythoncell().fromfile("AspectLayout.py")
ctx.registrar.python.register(ctx.aspect_layout)
ctx.display_numpy = reactor({
    "array": {"pin": "input", "dtype": "array"},
    "title": {"pin": "input", "dtype": "str"},
})
ctx.registrar.python.connect("AspectLayout", ctx.display_numpy)
ctx.array.connect(ctx.display_numpy.array)
ctx.title.connect(ctx.display_numpy.title)

ctx.display_numpy.code_update.set("update()")
ctx.display_numpy.code_stop.set("destroy()")
ctx.code = pythoncell()
ctx.code.connect(ctx.display_numpy.code_start)
ctx.code.fromfile("cell-display-numpy.py")
ctx.tofile("display_numpy.seamless", backup=False)

# For testing and debugging:
link(ctx.code)
ctx.gen_array = transformer({"array": {"pin": "output", "dtype": "array"}})
ctx.gen_array.array.connect(ctx.array)
link(ctx.gen_array.code.cell(), ".", "cell-gen-array.py")
