import seamless
import time
from seamless import cell, context, transformer, macro
from seamless.lib.gui.basic_editor import edit
from seamless.lib.gui.basic_display import display

@macro("str")
def construct_silk_model(ctx, mode):
    from seamless import transformer
    params = {"value": {"pin": "output", "dtype": "text"}}
    if mode == "array":
        params["N"] = {"pin": "input", "dtype": "int"}
        code = """s = SilkModel()
return str(SilkModelArray([s for n in range(N)]))
"""
    else:
        code = "return str(SilkModel())"
    ctx.transf = transformer(params)
    ctx.transf.code.cell().set(code)
    ctx.registrar.silk.connect("SilkModel", ctx.transf)
    if mode == "array":
        ctx.registrar.silk.connect("SilkModelArray", ctx.transf)
    ctx.export(ctx.transf)

ctx = context()
silk_model = """
Type SilkModel {
  Integer a = 1
  Float b = 2.0
  Bool c = True
  String x = "OK"
}
"""
silk_model2 = """
Type SilkModel {
  Integer a = 1
  Float b = 2.0
  Bool c = True
  String x = "OK2"
}
"""

ctx.silk_model = cell(("text", "code", "silk"))
ctx.silk_model.set(silk_model)
ctx.registrar.silk.register(ctx.silk_model)

ctx.n = cell("int").set(3)
ctx.mode = cell("str").set("standard")
ctx.value = cell("text")
ctx.cons = construct_silk_model(ctx.mode)
ctx.cons.value.connect(ctx.value)
ctx._validate_path()

ctx.silk_model.set(silk_model2)
time.sleep(0.001)
print(ctx.value.data)

ctx.ed_silk_model = edit(ctx.silk_model,"Silk model")
ctx._validate_path()

ctx.d_value = display(ctx.value,"Result")
ctx._validate_path()

ctx.mode.set("array")
ctx.n.connect(ctx.cons.N)

import os
ctx.tofile(os.path.splitext(__file__)[0] + ".seamless", backup=False)
