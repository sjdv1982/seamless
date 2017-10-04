from seamless.lib.gui.gl import glprogram

ctx.vert_shader = cell(("text", "code", "vertexshader"))
ctx.frag_shader = cell(("text", "code", "fragmentshader"))
link(ctx.vert_shader, ".", "vert_shader.glsl")
link(ctx.frag_shader, ".", "frag_shader.glsl")

ctx.program = cell("cson")
link(ctx.program, ".", "program.cson")
if not ctx.program.value: ### kludge: to be fixed in seamless 0.2
    ctx.program.set("{}")
p = ctx.glprogram = glprogram(ctx.program, window_title="Seamless fireworks demo")
ctx.glprogram.uniforms.set({})

ctx.frag_shader.connect(p.fragment_shader)
ctx.vert_shader.connect(p.vertex_shader)
ctx.vertexdata.set_store("GL")
ctx.vertexdata.connect(p.array_vertexdata)
