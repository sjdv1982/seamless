from ..decode import decode
from seamless.core import context, cell, transformer, macro_mode_on
from seamless.mixed.io import to_stream

def transform_job(rqdata):
    x = decode(rqdata, as_cells=True)
    transformer_params, output_signature, cells, _, _ = x
    inputs = cells.keys()
    with macro_mode_on():
        ctx = context(toplevel=True)
        tf = ctx.TRANSFORMER = transformer(transformer_params)
        for k in inputs:
            setattr(ctx, k, cells[k])
            cells[k].connect(getattr(tf, k))
        outputpin = getattr(tf, tf._output_name)
        for n, outp in enumerate(output_signature):
            name = "RESULT" + str(n+1)
            if outp == "mixed":
                c2 = cell("text")
                setattr(ctx, name + "_storage", c2)
                c3 = cell("json")
                setattr(ctx, name + "_form", c3)
                c = cell("mixed", storage_cell=c2, form_cell=c3)
            else:
                c = cell(outp)
            setattr(ctx, name, c)
            outputpin.connect(c)
    while tf.status() not in ("OK", "ERROR"):
        ctx.equilibrate(1)
    result = {}
    if tf.status() != "OK":
        result["ERROR"] = ctx.tf.transformer.EXCEPTION
    else:
        for n, outp in enumerate(output_signature):
            name = "RESULT" + str(n+1)
            data = getattr(ctx, name)
            if outp == "mixed":
                storage = getattr(ctx, name + "_storage")
                result["STORAGE"] = storage
                form = getattr(ctx, name + "_form")
                result["FORM"] = form                
            result[outp] = data
        for key, c in list(result.items()):
            val = c.serialize_buffer()
            result[key] = val
    return result
