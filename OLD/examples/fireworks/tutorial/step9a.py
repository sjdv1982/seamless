# Texture generator
ctx.params_gen_texture = cell(("cson", "seamless", "transformer_params"))
link(ctx.params_gen_texture, ".", "params_gen_texture.cson")
if not ctx.params_gen_texture.value: ### kludge: to be fixed in seamless 0.2
    ctx.params_gen_texture.set("{}")
ctx.gen_texture = transformer(ctx.params_gen_texture)
link(ctx.gen_texture.code.cell(), ".", "cell-gen-texture.py")
ctx.texture = cell("array")
ctx.texture.set_store("GLTex", 2) #OpenGL texture store, 2D texture
