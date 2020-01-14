# Program template
ctx.program_template = cell("cson")
link(ctx.program_template, ".", "program_template.cson")

ctx.gen_program = transformer({"program_template": {"pin": "input", "dtype": "json"},
                               "program": {"pin": "output", "dtype": "json"}})
ctx.registrar.silk.connect("VertexData", ctx.gen_program)
link(ctx.gen_program.code.cell(), ".", "cell-gen-program.py")
ctx.program_template.connect(ctx.gen_program.program_template)
ctx.gen_program.program.connect(ctx.program)
