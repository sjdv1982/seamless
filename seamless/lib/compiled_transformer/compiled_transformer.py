import numpy as np
from seamless.highlevel import Context, Cell, stdlib
from seamless.highlevel import set_resource

gen_header_file = "gen_header.py"
compiler_file = "compiler.py"
translator_file = "translator.py"

ctx = Context()

def gen_header(input_schema, result_schema, input_name, result_name, inputpins):
    return None
ctx.gen_header = gen_header
pins = ctx.gen_header._get_htf()["pins"] ###
pins["input_schema"]["access_mode"] = "json"
pins["result_schema"]["access_mode"] = "json"
pins["input_name"]["access_mode"] = "text"
pins["result_name"]["access_mode"] = "text"
ctx.gen_header.code = set_resource(gen_header_file)

ctx.compiler = lambda lang, header, compiled_code, main_module, compiler_verbose: None
ctx.compiler.code = set_resource(compiler_file)
pins = ctx.compiler._get_htf()["pins"] ###
pins["lang"]["access_mode"] = "text"
pins["compiled_code"]["access_mode"] = "text"
pins["header"]["access_mode"] = "text"
pins["main_module"]["access_mode"] = "json"
pins["compiler_verbose"]["access_mode"] = "json"

def func(binary_module, pins, input_schema, result_schema, input_name, result_name, kwargs):
    None

ctx.translator = func
ctx.translator.code = set_resource(translator_file)
ctx.translator.RESULT = "translator_result_"
pins = ctx.translator._get_htf()["pins"] ###
pins["binary_module"]["access_mode"] = "binary_module"
pins["input_schema"]["access_mode"] = "json"
pins["result_schema"]["access_mode"] = "json"
pins["input_name"]["access_mode"] = "text"
pins["result_name"]["access_mode"] = "text"

ctx.translate()

gen_header_params = ctx.gen_header._get_tf().tf._transformer_params
ctx.gen_header_params = gen_header_params
ctx.gen_header_params.celltype = "json"

compiler_params = ctx.compiler._get_tf().tf._transformer_params
ctx.compiler_params = compiler_params
ctx.compiler_params.celltype = "json"

translator_params = ctx.translator._get_tf().tf._transformer_params
ctx.translator_params = translator_params
ctx.translator_params.celltype = "json"

if __name__ == "__main__":
    ctx.mount("/tmp/seamless-test", persistent=False) #TODO: persistent=False (does not delete atm)

    # 1. Set up topology as it will be in the real world
    ctx.header = ctx.gen_header
    ctx.header.celltype = "text"

    ctx.inputpins = Cell()
    ctx.inputpins.celltype = "json"

    ctx.input_schema = Cell()
    ctx.input_schema.celltype = "json"

    ctx.result_schema = Cell()
    ctx.result_schema.celltype = "json"

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

    ctf = ctx.compiler
    ctf.header = ctx.header
    ctx.binary_module = ctx.compiler

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
    ctx.cppcode.celltype = "text"

    ctx.tf0 = lambda a,b: a + b
    ctx.tf0.example.a = 0
    ctx.tf0.example.b = 0
    ctx.tf0.with_result = True
    ctx.tf0.result.example = 0.0

    ctf = ctx.compiler
    ctf.compiled_code = ctx.cppcode
    ctf.lang = "cpp"
    ctf.main_module = {
        "link_options" : ["-lm"],
    }
    ctf.compiler_verbose = True

    #connect the schema's; just the values, for now... #TODO: pins!
    ctx.input_schema = ctx.tf0.inp.schema._dict
    ctx.result_schema = ctx.tf0.result.schema._dict #TODO: solve inconsistency...
    ctx.input_name = ctx.tf0._get_htf()["INPUT"]
    ctx.result_name = ctx.tf0._get_htf()["RESULT"]

    pins = ctx.tf0._get_tf().tf._transformer_params ### convoluted way to access, but nothing we can do
    ctx.translator.pins = pins
    inputpins = [k for k,v in pins.items() if \
      (isinstance(v,str) and v == "input") or \
      (isinstance(v,dict) and v["io"] == "input") ]
    ctx.inputpins.set(inputpins)

    ctx.kwargs = {"a": 2, "b": 3}

    ctx.equilibrate()
else:
    stdlib.compiled_transformer = ctx
