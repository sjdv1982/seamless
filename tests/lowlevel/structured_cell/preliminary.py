from seamless.core import (
    context, cell, transformer, macro_mode_on
)    
from seamless.core.structured_cell import StructuredCell
from pprint import pprint
import time

def progress(limit, delay, factor, offset):
    import time
    for n in range(limit):
        return_preliminary(factor*n + offset)
        set_progress(100* (n+1)/limit)
        time.sleep(delay)
    return factor * limit + offset

def structured_transformer(c):
    tf_params = {
        "limit": ("input", "int"),
        "delay": ("input", "float"),
        "factor": ("input", "float"),
        "offset": ("input", "float"),
        "result": ("output", "float"),
    }    
    c.tf = transformer(tf_params)
    c.code = cell("transformer").set(progress)
    c.code.connect(c.tf.code)
    c.input_data = cell("mixed")
    c.input_buffer = cell("mixed")
    c.input_schema = cell("plain")
    c.input = StructuredCell(
        data=c.input_data,
        buffer=c.input_buffer,
        schema=c.input_schema,
        inchannels=[()],
        outchannels=[(k,) for k in tf_params.keys() if k != "result"],
    )
    c.result = cell("mixed")
    c.tf.result.connect(c.result)
    for param in tf_params:
        if param == "result":
            continue
        icellname = "input_param_" + param
        icell = cell("mixed")
        setattr(c, icellname, icell)
        outchannel = c.input.outchannels[(param,)]
        pin = getattr(c.tf, param)
        outchannel.connect(icell)
        icell.connect(pin)
    c.example_data = cell("mixed")
    c.example_buffer = cell("mixed")
    c.example = StructuredCell(
        data=c.example_data,
        buffer=c.example_buffer,
        schema=c.input_schema
    )

with macro_mode_on():
    ctx = context(toplevel=True)

    ctx.params_struc = context()
    ctx.params_struc.data = cell("mixed")
    ctx.params = StructuredCell(
        ctx.params_struc.data,
        outchannels = [("tf1",),("tf2",),("tf3",),("tf4",)] # TODO: try numeric path
    )    
    
    ctx.stf1 = context(toplevel=False)
    structured_transformer(ctx.stf1)
    ctx.stf2 = context(toplevel=False)
    structured_transformer(ctx.stf2)
    ctx.stf3 = context(toplevel=False)
    structured_transformer(ctx.stf3)
    ctx.stf4 = context(toplevel=False)
    structured_transformer(ctx.stf4)

    ctx.result_struc = context()
    ctx.result_struc.data = cell("mixed")
    ctx.result_struc.buffer = cell("mixed")
    ctx.result_struc.schema = cell("plain")
    ctx.result = StructuredCell(
        ctx.result_struc.data,
        buffer = ctx.result_struc.buffer,
        schema = ctx.result_struc.schema,
        inchannels = [("tf1",),("tf2",),("tf3",),("tf4",)] # TODO: try numeric path
    )
    
    ctx.params_struc.outchannel_tf1 = cell("mixed")
    ctx.params.outchannels[("tf1",)].connect(ctx.params_struc.outchannel_tf1)
    ctx.params_struc.outchannel_tf1.connect(ctx.stf1.input.inchannels[()])

    ctx.stf1.result.connect(ctx.result.inchannels[("tf1",)]) 
    """
    ctx.add = transformer(add_params)
    ctx.add.code.set("result = a + b")
    ctx.tf1.result.connect(ctx.add.a.cell())
    ctx.tf2.result.connect(ctx.add.b.cell())
    ctx.add.result.connect(ctx.tf3.offset.cell())
    ctx.add.result.connect(ctx.tf4.offset.cell())
    """
    # TODO: "add" in the result.schema

ctx.params.handle.set({
    "tf1": {},
    "tf2": {},
    "tf3": {},
    "tf4": {},
})

h = ctx.params.handle.tf1
h.limit = 9
h.factor = 1000
h.delay = 1.5
h.offset = 0

"""    
ctx.tf2.limit.cell().set(15)
ctx.tf2.factor.cell().set(10)
ctx.tf2.delay.cell().set(0.7)
ctx.tf2.offset.cell().set(0)
ctx.tf2_result = ctx.tf2.result.cell()

ctx.tf3.limit.cell().set(9)
ctx.tf3.factor.cell().set(1)
ctx.tf3.delay.cell().set(0.5)
ctx.tf3_result = ctx.tf3.result.cell()

ctx.tf4.limit.cell().set(1)
ctx.tf4.factor.cell().set(9)
ctx.tf4.delay.cell().set(0.1)
ctx.tf4_result = ctx.tf4.result.cell()
"""

state = {}
oldstate = {}
start = time.time()
while 1:
    waitfor, background = ctx.equilibrate(0.01, report=None)
    state["status"] = {
        "tf1": ctx.stf1.tf.status
    }
    state["status"]["tf1-result"] = ctx.stf1.result.status

    state["tf1"] = ctx.stf1.tf.value
    state["tf1-result"] = ctx.stf1.result.value
    if state != oldstate:
        print("Time elapsed: %.3f" % (time.time() - start))
        pprint(state)
        print()
        oldstate = state.copy()
    if not len(waitfor) and not background:        
        break
    
print(ctx.params.value)
print(ctx.params_struc.outchannel_tf1.value)
#print(ctx.stf1.input.value)