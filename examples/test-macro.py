import seamless
import time
from seamless import cell, context, transformer, macro
from seamless.lib.gui.basic_editor import edit
from seamless.lib.gui.basic_display import display

@macro("str")
def construct_silk_model(ctx, mode):
    print("CONSTRUCT", mode)
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
    #ctx.export(ctx.transf)
    ctx._like_process = True ###

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
import seamless
#types = seamless.silk.register(silk_model2)
#seamless.silk.unregister(types)
#types = seamless.silk.register(silk_model)
#obj = ctx.registrar.silk.register(silk_model)

ctx.silk_model = cell(("text", "code", "silk"))
ctx.silk_model.set(silk_model)
ctx.registrar.silk.register(ctx.silk_model)
time.sleep(0.001)
print(seamless.silk.Silk.SilkModel())

ctx.n = cell("int")
ctx.mode = cell("str").set("standard")
ctx.value = cell("text")
ctx.cons = construct_silk_model(ctx.mode)

#ctx.cons.transf.value.connect(ctx.value)
#time.sleep(0.001)
time.sleep(0.001)
ctx._validate_path()

ctx.silk_model.set(silk_model2)
time.sleep(0.001)
print(ctx.value.data)

ctx.ed_silk_model = edit(ctx.silk_model,"Silk model")
ctx._validate_path()

#ctx.d_value = display(ctx.value,"Result")
#ctx.d_value = display(ctx.cons.transf.value.cell(),"Result")

from seamless.core.context import get_active_context
print("ACTIVE?", get_active_context())
#import sys
#sys.exit()

ctx.ed_value = edit(ctx.cons.transf.value.cell(),"Result",solid=False)
ctx._validate_path()

print(ctx.cons.transf.code.cell())
print(ctx.cons.transf.value.cell())
print(list(ctx.cons._children.keys()))
#import sys
#sys.exit()

#TODO: above works, but below still fails:
ctx.mode.set("array")
