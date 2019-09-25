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
    try:
        print("Offset:", self.offset.unsilk)
    except AttributeError:
        pass
    print("")

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
    c.input_auth = cell("mixed")
    c.input_data = cell("mixed")
    c.input_buffer = cell("mixed")
    c.input_schema = cell("plain")
    c.input = StructuredCell(
        data=c.input_data,
        auth=c.input_auth,
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
    channel_names = tf_names # TODO (long term): try numeric path

    ctx.params_struc = context()
    ctx.params_struc.data = cell("mixed")
    ctx.params_struc.auth = cell("mixed")
    ctx.params_struc.buffer = cell("mixed")
    ctx.params_struc.schema = cell("plain")
    ctx.params_struc.example_buffer = cell("mixed")
    ctx.params_struc.example_data = cell("mixed")    
    ctx.params = StructuredCell(
        ctx.params_struc.data,
        auth=ctx.params_struc.auth,
        buffer=ctx.params_struc.buffer,
        schema=ctx.params_struc.schema,
        inchannels=[tf_names[2] + ("offset",), tf_names[3] + ("offset",)],
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
        setattr(ctx, "result_" + tf_name[0], channel_cell)
        ctx.result.outchannels[outchannel].connect(channel_cell)

    
    for n in range(4): 
        channel_name, tf_name = channel_names[n], tf_names[n]
        c = cell("mixed")
        cell_name = "outchannel_" + tf_name[0]
        setattr(ctx.params_struc, cell_name, c) 
        ctx.params.outchannels[channel_name].connect(c)
        stf = getattr(ctx, "stf" + str(n+1))
        c.connect(stf.input.inchannels[()])
        stf.result.connect(ctx.result.inchannels[channel_name]) 
    
    add_params = {
        "a": ("input", "float"),
        "b": ("input", "float"),
        "result": ("output", "float"),
    }

    ctx.add = transformer(add_params)
    ctx.add.code.set("result = a + b")
    tf1, tf2, tf3, tf4 = tf_names
    ctx.result.outchannels[tf1].connect(ctx.add.a.cell())
    ctx.result.outchannels[tf2].connect(ctx.add.b.cell())
    ctx.add.result.cell().connect(ctx.params.inchannels[tf3 + ("offset",)])
    ctx.add.result.cell().connect(ctx.params.inchannels[tf4 + ("offset",)])
    
    
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
#hh.offset = 0.0 # offset can be optional
def validate_param(self):
    assert self.delay > 0
    assert self.limit < 100
hh.add_validator(validate_param)

for tf in channel_names[1:]:
    h[tf[0]] = h[first]
    hh = h[tf[0]]
    hh.schema.set(h[channel_names[0][0]].schema)


hh = ctx.params.handle.tf1
hh.limit = 9
hh.factor = 1000
hh.delay = 1.5
hh.offset = 0

hh = ctx.params.handle.tf2
hh.limit = 15
hh.factor = 10
hh.delay = 0.7
hh.offset = 0

hh = ctx.params.handle.tf3
hh.limit = 9
hh.factor = 1
hh.delay = 0.5
#hh.offset = 0

hh = ctx.params.handle.tf4
hh.limit = 1
hh.factor = 9
hh.delay = 0.1
#hh.offset = 0

ctx.equilibrate(0.1)
ctx.params.handle.report()
ctx.params.handle.tf1.validate()


for c in (ctx.stf1, ctx.stf2, ctx.stf3, ctx.stf4): 
    h = c.example.handle
    h.subreport = subreport
    def v(self):
        try:
            offset = self.offset
        except AttributeError:
            return
        if offset.unsilk is None:
            return
        assert offset == 0 or offset > 2000 or self.factor == 9
    h.add_validator(v)

ctx.equilibrate(0.1)

state = {}
oldstate = {}
start = time.time()
while 1:
    waitfor, background = ctx.equilibrate(0.01, report=None)
    state["status"] = {
        "tf1": ctx.stf1.tf.status,
        "tf2": ctx.stf2.tf.status,
        "tf3": ctx.stf3.tf.status,
        "tf4": ctx.stf4.tf.status,
    }
    state["status"]["tf1-result"] = ctx.result_tf1.status
    state["status"]["tf2-result"] = ctx.result_tf2.status
    state["status"]["tf3-result"] = ctx.result_tf3.status
    state["status"]["tf4-result"] = ctx.result_tf4.status

    state["tf1"] = ctx.stf1.tf.value
    state["tf1-result"] = ctx.result_tf1.value
    state["tf2"] = ctx.stf2.tf.value
    state["tf2-result"] = ctx.result_tf2.value
    state["tf3"] = ctx.stf3.tf.value
    state["tf3-result"] = ctx.result_tf3.value
    state["tf4"] = ctx.stf4.tf.value
    state["tf4-result"] = ctx.result_tf4.value
    if state != oldstate:
        print("Time elapsed: %.3f" % (time.time() - start))
        pprint(state)
        exc = ctx.stf3.input.exception
        if exc is not None:
            print(exc)
        print()
        #ctx.params.value.report()
        oldstate = state.copy()
    if not len(waitfor) and not background:        
        break
    
ctx.params.value.report()
print(ctx.params.value.tf3)