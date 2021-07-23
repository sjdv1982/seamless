import sys

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

###ctx.mount("/tmp/seamless-test", persistent=False)
ctx.testdata = "a\nb\nc\nd\ne\nf\n"
ctx.docker_command = "head -$lines testdata > firstdata; mkdir -p RESULT/input; cp firstdata RESULT; cp testdata RESULT/input"
ctx.executor = lambda docker_command, docker_image_, docker_options, pins_, testdata, lines: None
pins = ctx.executor.pins
pins.docker_command.celltype = "str"
pins.docker_image_.celltype = "str"
pins.pins_.celltype = "plain"
ctx.executor.pins_ = ["lines", "testdata"]
pins["lines"]["celltype"] = "int"
pins["testdata"]["celltype"] = "text"
ctx.executor.code = ctx.executor_code
ctx.executor.docker_command = ctx.docker_command
ctx.executor.docker_image_ = "ubuntu"
ctx.executor.docker_options = {}
ctx.executor.testdata = ctx.testdata
ctx.executor.lines = 3
ctx.result = ctx.executor
ctx.result.celltype = "text"
ctx.compute()
print(ctx.result.value)
print()
ctx.executor.lines = 4
ctx.compute()
print(ctx.result.value)

if ctx.result.value is None:
    print(ctx.executor_code.exception)
    print(ctx.executor.status)
    print(ctx.executor.inp.exception)
    print(ctx.executor.exception)
    print(ctx.status)
    import sys
    sys.exit()

# 3: Save graph and zip

import os, json
currdir=os.path.dirname(os.path.abspath(__file__))
graph_filename=os.path.join(currdir,"../bashdocker_transformer.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename=os.path.join(currdir,"../bashdocker_transformer.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)

from seamless.core.cache.transformation_cache import transformation_cache
sem_checksum = transformation_cache.syntactic_to_semantic(
    bytes.fromhex(ctx.executor.code.checksum), "python", "transformer", ""
)
print("Executor semantic code checksum:", sem_checksum.hex())