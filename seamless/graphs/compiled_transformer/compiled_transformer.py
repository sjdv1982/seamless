import sys
from seamless.highlevel import Context, Cell
from seamless.highlevel import set_resource


gen_header_file = "gen_header.py"
integrator_file = "integrator.py"
executor_file = "executor.py"

ctx = Context()

def gen_header(input_schema, result_schema, input_name, result_name, inputpins):
    return None
ctx.gen_header = gen_header
pins = ctx.gen_header.pins
pins["input_schema"]["celltype"] = "plain"
pins["result_schema"]["celltype"] = "plain"
pins["input_name"]["celltype"] = "str"
pins["result_name"]["celltype"] = "str"

ctx.gen_header.code = set_resource(gen_header_file)

ctx.integrator = lambda lang, header_, compiled_code, main_module, debug_: None
ctx.integrator.code = set_resource(integrator_file)
pins = ctx.integrator.pins
pins["debug_"]["celltype"] = "bool"
pins["lang"]["celltype"] = "str"
pins["compiled_code"]["celltype"] = "text"
pins["header_"]["celltype"] = "text"
pins["header_"]["as_"] = "header"
pins["main_module"]["celltype"] = "plain"

def func(module, pins, input_schema, result_schema, input_name, result_name, kwargs):
    None

ctx.executor = func
ctx.executor.add_special_pin("SPECIAL__DIRECT_PRINT", "bool")
ctx.executor.code = set_resource(executor_file)
pins = ctx.executor.pins
pins["module"]["celltype"] =  "module"
pins["input_schema"]["celltype"] = "plain"
pins["result_schema"]["celltype"] = "plain"
pins["input_name"]["celltype"] = "text"
pins["result_name"]["celltype"] = "text"

ctx.translate()
gen_header_params = ctx.gen_header._get_tf().tf._transformer_params
ctx.gen_header_params = gen_header_params
ctx.gen_header_params.celltype = "plain"

integrator_params = ctx.integrator._get_tf().tf._transformer_params
ctx.integrator_params = integrator_params
ctx.integrator_params.celltype = "plain"

executor_params = ctx.executor._get_tf().tf._transformer_params
ctx.executor_params = executor_params
ctx.executor_params.celltype = "plain"

# 1. Set up topology as it will be in the real world
ctx.header = ctx.gen_header
ctx.header.celltype = "text"

ctx.inputpins = Cell()
ctx.inputpins.celltype = "plain"

ctx.input_schema = Cell()
ctx.input_schema.celltype = "plain"

ctx.result_schema = Cell()
ctx.result_schema.celltype = "plain"

ctx.input_name = Cell()
ctx.input_name.celltype = "text"

ctx.result_name = Cell()
ctx.result_name.celltype = "text"

ctx.gen_header.inputpins = ctx.inputpins
ctx.gen_header.input_schema = ctx.input_schema
ctx.gen_header.result_schema = ctx.result_schema
ctx.gen_header.input_name = ctx.input_name
ctx.gen_header.result_name = ctx.result_name

ctf = ctx.integrator
ctf.header_ = ctx.header
ctx.module = ctx.integrator

ctf = ctx.executor
ctf.input_schema = ctx.input_schema
ctf.result_schema = ctx.result_schema
ctf.input_name = ctx.input_name
ctf.result_name = ctx.result_name
ctf["SPECIAL__DIRECT_PRINT"] = False
ctx.result = ctx.executor
ctx.result.celltype = "float"

ctx.kwargs = Cell()
ctf.kwargs = ctx.kwargs
ctx.translate()

# 2: obtain graph and zip

graph = ctx.get_graph()
zip = ctx.get_zip()

# 3: Test with values for a specific example

ctx.cppcode = set_resource("test.cpp")
ctx.cppcode.celltype = "code"
ctx.cppcode.language = "cpp"

ctx.tf0 = lambda a,b: a + b
ctx.translate()
ctx.tf0.example.a = 0
ctx.tf0.example.b = 0
ctx.tf0.result.example = 0.0

ctf = ctx.integrator
ctf.debug_ = False
ctf.compiled_code = ctx.cppcode
ctf.lang = "cpp"
ctf.main_module = {
    "link_options" : ["-lm"],
}

ctx.input_schema = ctx.tf0.schema
ctx.result_schema = ctx.tf0.result.schema
ctx.input_name = ctx.tf0._get_htf()["INPUT"]
ctx.result_name = ctx.tf0._get_htf()["RESULT"]

pins = ctx.tf0._get_tf().tf._transformer_params ### convoluted way to access, but nothing we can do
ctx.executor.pins = pins
inputpins = [k for k,v in pins.items() if \
    (isinstance(v,str) and v == "input") or \
    (isinstance(v,dict) and v["io"] == "input") ]
ctx.inputpins.set(inputpins)

ctx.kwargs = {"a": 2, "b": 3}
ctx.executor.kwargs = ctx.kwargs
ctx.executor.module = ctx.module

ctx.compute()
if ctx.result.value is None:
    print("ERROR")
    print(ctx.gen_header.status)
    print(ctx.gen_header.exception)
    print(ctx.integrator.status)
    print(ctx.integrator.exception)
    print(ctx.executor.status)
    print(ctx.executor.exception)
    sys.exit()

print(ctx.executor.logs)

# 4: Save graph and zip

import os, json
currdir=os.path.dirname(os.path.abspath(__file__))
graph_filename=os.path.join(currdir,"../compiled_transformer.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename=os.path.join(currdir,"../compiled_transformer.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)