from seamless.core import context, cell, transformer, macro_mode_on
from pprint import pprint
import time

def progress(limit, delay, factor, offset):
    import time
    for n in range(limit):
        return_preliminary(factor*n + offset)
        set_progress(100* (n+1)/limit)
        time.sleep(delay)
    return factor * limit + offset

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.mount("/tmp/mount-seamless", persistent=None)
    ctx.progress = cell("transformer").set(progress)
    tf_params = {
        "limit": ("input", "int"),
        "delay": ("input", "float"),
        "factor": ("input", "float"),
        "offset": ("input", "float"),
        "result": ("output", "float"),
    }
    add_params = {
        "a": ("input", "float"),
        "b": ("input", "float"),
        "result": ("output", "float"),
    }
    ctx.tf1 = transformer(tf_params)
    ctx.tf2 = transformer(tf_params)
    ctx.tf3 = transformer(tf_params)
    ctx.tf4 = transformer(tf_params)

    ctx.progress.connect(ctx.tf1.code)
    ctx.progress.connect(ctx.tf2.code)
    ctx.progress.connect(ctx.tf3.code)
    ctx.progress.connect(ctx.tf4.code)

    ctx.tf1.limit.cell().set(9)
    ctx.tf1.factor.cell().set(1000)
    ctx.tf1.delay.cell().set(0.7)
    ctx.tf1.offset.cell().set(0)    
    
    ctx.tf2.limit.cell().set(12)
    ctx.tf2.factor.cell().set(10)
    ctx.tf2.delay.cell().set(2)
    ctx.tf2.offset.cell().set(0)
    
    ctx.tf3.limit.cell().set(9)
    ctx.tf3.factor.cell().set(1)
    ctx.tf3.delay.cell().set(0.5)
    ctx.tf3.result.cell()    
    ctx.tf4.limit.cell().set(1)
    ctx.tf4.factor.cell().set(9)
    ctx.tf4.delay.cell().set(0.1)
    ctx.tf4.result.cell()
    
    ctx.add = transformer(add_params)
    ctx.add.code.set("result = a + b")
    ctx.tf1.result.connect(ctx.add.a.cell())
    ctx.tf2.result.connect(ctx.add.b.cell())
    ctx.add.result.connect(ctx.tf3.offset.cell())
    ctx.add.result.connect(ctx.tf4.offset.cell())

state = {}
oldstate = {}
start = time.time()
while 1:
    waitfor, background = ctx.equilibrate(0.01, report=None)
    state["status"] = {"tf1": ctx.tf1.status, "tf2": ctx.tf2.status, "tf3": ctx.tf3.status, "tf4": ctx.tf4.status}
    state["status"]["tf1-result"] = ctx.tf1.result.cell().status
    state["status"]["tf2-result"] = ctx.tf2.result.cell().status
    state["status"]["tf3-result"] = ctx.tf3.result.cell().status
    state["status"]["tf4-result"] = ctx.tf4.result.cell().status

    state["tf1"] = ctx.tf1.value
    state["tf1-result"] = ctx.tf1.result.cell().value
    state["tf2"] = ctx.tf2.value
    state["tf2-result"] = ctx.tf2.result.cell().value
    state["tf3"] = ctx.tf3.value
    state["tf3-result"] = ctx.tf3.result.cell().value
    state["tf4"] = ctx.tf4.value
    state["tf4-result"] = ctx.tf4.result.cell().value 
    if state != oldstate:
        print("Time elapsed: %.3f" % (time.time() - start))
        pprint(state)
        print()
        oldstate = state.copy()
    if not len(waitfor) and not background:        
        break
    