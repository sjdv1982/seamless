from seamless.highlevel import Context, Cell
from seamless.highlevel import set_resource

executor_file = "executor.py"

# 1: Setup

ctx = Context()
ctx.executor_code = set_resource(executor_file)
ctx.executor_code._get_hcell()["language"] = "python"
ctx.executor_code._get_hcell()["transformer"] = True
ctx.executor_code.celltype = "code"
ctx.translate()

# 2: obtain graph and zip

graph = ctx.get_graph()
zip = ctx.get_zip()


# 3: Run test example

#ctx.mount("/tmp/seamless-test", persistent=False) #TODO: persistent=False (does not delete atm)
ctx.testdata = "a\nb\nc\nd\ne\nf\n"       
ctx.bashcode = "head -$lines testdata"
ctx.executor = lambda bashcode, testdata, pins_, lines: None
pins = ctx.executor.pins
pins.bashcode.celltype = "text"
pins.pins_.celltype = "plain"
ctx.executor.pins_ = ["lines", "testdata"]
pins["lines"]["celltype"] = "int"
pins["testdata"]["celltype"] = "text"
ctx.executor.code = ctx.executor_code
ctx.executor.bashcode = ctx.bashcode
ctx.executor.testdata = ctx.testdata    
ctx.executor.lines = 3
ctx.result = ctx.executor
ctx.result.celltype = "text"
ctx.equilibrate()
print(ctx.result.value)
print()
ctx.executor.lines = 4
ctx.equilibrate()
print(ctx.result.value)

if ctx.result.value is None:
    sys.exit()

# 3: Save graph and zip

import os, json
currdir=os.path.dirname(os.path.abspath(__file__))
graph_filename=os.path.join(currdir,"../bash_transformer.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename=os.path.join(currdir,"../bash_transformer.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)