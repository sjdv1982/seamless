from seamless import macro

@macro(type=("json", "seamless", "transformer_params"))
def itransformer(ctx, params):
    from seamless import editor
    from seamless.core.process import ExportedInputPin
    params2 = params.copy()
    params2["code"] = {"pin": "input",
                        "dtype": ("text", "code", "ipython")}
    params2["transformer_params"] = {"pin": "input", "dtype": "json"}
    ed = ctx.ed = editor(params2)
    ed.transformer_params.cell().set(params)
    ed.code_start.cell().fromfile("cell-itransformer.py")
    ed.code_update.cell().set("do_update()")
    ed.code_stop.cell().set("")
    ctx.export(ctx.ed)
