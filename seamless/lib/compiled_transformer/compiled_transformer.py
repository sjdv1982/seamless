import numpy as np
from seamless.highlevel import Context, Cell, stdlib
from seamless.highlevel import set_resource

gen_header_file = "gen_header.py"
integrator_file = "integrator.py"
translator_file = "translator.py"

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

ctx.integrator = lambda lang, header, compiled_code, main_module, debug_: None
ctx.integrator.code = set_resource(integrator_file)
pins = ctx.integrator.pins
pins["debug_"]["celltype"] = "bool"
pins["lang"]["celltype"] = "str"
pins["compiled_code"]["celltype"] = "text"
pins["header"]["celltype"] = "text"
pins["main_module"]["celltype"] = "plain"

def func(module, pins, input_schema, result_schema, input_name, result_name, kwargs):
    None

ctx.translator = func
ctx.translator.code = set_resource(translator_file)
ctx.translator.RESULT = "translator_result_"
pins = ctx.translator._get_htf()["pins"] ### need to access like this; TODO: implement .self.pins
pins["module"]["celltype"] =  "plain"
pins["module"]["subcelltype"] =  "module"
pins["input_schema"]["celltype"] = "plain"
pins["result_schema"]["celltype"] = "plain"
pins["input_name"]["celltype"] = "text"
pins["result_name"]["celltype"] = "text"

gen_header_params = ctx.gen_header._get_tf().tf._transformer_params
ctx.gen_header_params = gen_header_params
ctx.gen_header_params.celltype = "plain"

integrator_params = ctx.integrator._get_tf().tf._transformer_params
ctx.integrator_params = integrator_params
ctx.integrator_params.celltype = "plain"

translator_params = ctx.translator._get_tf().tf._transformer_params
ctx.translator_params = translator_params
ctx.translator_params.celltype = "plain"

if __name__ == "__main__":
    ctx.mount("/tmp/seamless-test", persistent=False)

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

    ctx.print_header = lambda header: print("HEADER", header)
    ctx.print_header.header = ctx.header

    ctf = ctx.integrator
    ctf.header = ctx.header
    ctx.module = ctx.integrator

    ctf = ctx.translator
    ctf.input_schema = ctx.input_schema
    ctf.result_schema = ctx.result_schema
    ctf.input_name = ctx.input_name
    ctf.result_name = ctx.result_name
    ctx.result = ctx.translator

    ctx.kwargs = Cell()
    ctf.kwargs = ctx.kwargs

    ctx.print_result = lambda result_: print("RESULT", result_)
    ctx.print_result.result_ = ctx.result

    # 2: Set up the values for a specific example
    ctx.cppcode = set_resource("test.cpp")
    ctx.cppcode.celltype = "code"
    ctx.cppcode.language = "cpp"

    ctx.tf0 = lambda a,b: a + b
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
    ctx.translator.pins = pins
    inputpins = [k for k,v in pins.items() if \
      (isinstance(v,str) and v == "input") or \
      (isinstance(v,dict) and v["io"] == "input") ]
    ctx.inputpins.set(inputpins)

    ctx.kwargs = {"a": 2, "b": 3}
    ctx.translator.kwargs = ctx.kwargs
    ctx.translator.module = ctx.module

    ctx.equilibrate()
else:
    stdlib.compiled_transformer = ctx
    