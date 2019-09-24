from seamless.core import (
    context, cell, transformer, macro_mode_on
)    
from seamless.core.structured_cell import StructuredCell
from seamless.silk import Silk
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
    tf_names = [("tf1",),("tf2",),("tf3",),("tf4",)] 
    channel_names = tf_names # TODO: try numeric path

    ctx.params_struc = context()
    ctx.params_struc.data = cell("mixed")
    ctx.params_struc.buffer = cell("mixed")
    ctx.params_struc.schema = cell("plain")
    ctx.params_struc.example_buffer = cell("mixed")
    ctx.params_struc.example_data = cell("mixed")    
    ctx.params = StructuredCell(
        ctx.params_struc.data,
        buffer=ctx.params_struc.buffer,
        schema=ctx.params_struc.schema,
        outchannels=channel_names
    )    
    ctx.params_example = StructuredCell(
        ctx.params_struc.example_data,
        buffer=ctx.params_struc.example_buffer,
        schema=ctx.params_struc.schema,
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
    outchannels = []

    ctx.result = StructuredCell(
        ctx.result_struc.data,
        buffer = ctx.result_struc.buffer,
        schema = ctx.result_struc.schema,
        inchannels = channel_names,
        outchannels = channel_names
    )
    for outchannel, tf_name in zip(channel_names, tf_names):
        channel_cell = cell("mixed")
        setattr(ctx, "result_" + outchannel[0], channel_cell)
        ctx.result.outchannels[outchannel].connect(channel_cell)

    
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

def report(self):
    print("*" * 80)
    print("*  PARAMETERS")
    print("*" * 80)
    for key in self.keys():                
        sub = self[key]
        if not len(sub):
            continue
        print("KEY", key)
        sub.subreport()
    print("*" * 80)
    print("")

def subreport(self):
    print("Limit:", self.limit.unsilk)
    print("Factor:", self.factor.unsilk)
    print("Delay:", self.delay.unsilk)
    print("Offset:", self.offset.unsilk)
    print("")

ctx.params.handle.set({
    "tf1": {},
    "tf2": {},
    "tf3": {},
    "tf4": {},
})

first = channel_names[0][0]
h = ctx.params_example.handle
h.report = report
h[first] = {}
hh = h[first]
hh.subreport = subreport
hh.limit = 0
hh.factor = 0.0
hh.delay = 0.1
hh.offset = 0.0
def validate_param(self):
    assert self.delay > 0
    assert self.limit < 100
hh.add_validator(validate_param)

for tf in channel_names[1:]:
    h[tf[0]] = h[first]
    hh = h[tf[0]]
    hh.schema.set(h[channel_names[0][0]].schema)


h = ctx.params.handle.tf1
h.limit = 9
h.factor = 1000
h.delay = 1.5
h.offset = 0


h = ctx.params.handle.tf2
h.limit = 15
h.factor = 10
h.delay = 0.7
h.offset = 0

ctx.equilibrate(0.1)
#hh.validate()
import sys; sys.exit()

"""    

ctx.tf3.limit.cell().set(9)
ctx.tf3.factor.cell().set(1)
ctx.tf3.delay.cell().set(0.5)
ctx.tf3_result = ctx.tf3.result.cell()

ctx.tf4.limit.cell().set(1)
ctx.tf4.factor.cell().set(9)
ctx.tf4.delay.cell().set(0.1)
ctx.tf4_result = ctx.tf4.result.cell()
"""


#ctx.params_example.handle.report()

ctx.params.handle.report()
ctx.params.handle.tf1.validate()
import sys; sys.exit()

state = {}
oldstate = {}
start = time.time()
while 1:
    waitfor, background = ctx.equilibrate(0.01, report=None)
    state["status"] = {
        "tf1": ctx.stf1.tf.status
    }
    state["status"]["tf1-result"] = ctx.result_tf1.status

    state["tf1"] = ctx.stf1.tf.value
    state["tf1-result"] = ctx.result_tf1.value
    if state != oldstate:
        print("Time elapsed: %.3f" % (time.time() - start))
        pprint(state)
        print()
        oldstate = state.copy()
    if not len(waitfor) and not background:        
        break
    
print(ctx.params.report())