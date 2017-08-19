from seamless import macro

@macro(type=("json", "seamless", "transformer_params"))
def itransformer(ctx, params):
    from seamless import reactor
    from seamless.core.worker import ExportedInputPin
    params2 = params.copy()
    params2["code"] = {"pin": "input",
                        "dtype": ("text", "code", "ipython")}
    if "html" not in params:
        params2["html"] = {"pin": "output",
                            "dtype": ("text", "html")}
    params2["transformer_params"] = {"pin": "input", "dtype": "json"}
    params2["@shell"] =  ".namespace"
    rc = ctx.rc = reactor(params2)
    rc.transformer_params.cell().set(params)
    rc.code_start.cell().fromfile("cell-itransformer.py")
    rc.code_update.cell().set("do_update()")
    rc.code_stop.cell().set("")
    ctx.export(ctx.rc)
