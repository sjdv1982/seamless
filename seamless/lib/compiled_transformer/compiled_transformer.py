import numpy as np
from seamless.highlevel import Context, Cell, stdlib
from seamless.lib import set_resource

gen_header_file = "gen_header.py"
compiler_file = "compiler.py"
translator_file = "translator.py"

ctx = Context()

ctx.gen_header = lambda input_schema, result_schema: None
pins = ctx.gen_header._get_htf()["pins"] ###
pins["input_schema"]["access_mode"] = "json"
pins["result_schema"]["access_mode"] = "json"
ctx.gen_header.code = set_resource(gen_header_file)

ctx.compiler = lambda language, header, compiled_code, main_module, compiler_verbose: None
ctx.compiler.code = set_resource(compiler_file)
pins = ctx.compiler._get_htf()["pins"] ###
pins["language"]["access_mode"] = "text"
pins["compiled_code"]["access_mode"] = "text"
pins["header"]["access_mode"] = "text"
pins["main_module"]["access_mode"] = "json"
pins["compiler_verbose"]["access_mode"] = "json"

ctx.translator = lambda binary_module, pins, input_schema, result_schema, kwargs: None
ctx.translator.code = set_resource(translator_file)
pins = ctx.translator._get_htf()["pins"] ###
pins["binary_module"]["access_mode"] = "binary_module"
pins["input_schema"]["access_mode"] = "json"
pins["result_schema"]["access_mode"] = "json"

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

    ctx.input_schema = Cell()
    ctx.input_schema.celltype = "json"

    ctx.result_schema = Cell()
    ctx.result_schema.celltype = "json"

    ctx.gen_header.input_schema = ctx.input_schema
    ctx.gen_header.result_schema = ctx.result_schema

    ctx.print_header = lambda header: print("HEADER", header)
    ctx.print_header.header = ctx.header

    ctf = ctx.compiler
    ctf.header = ctx.header
    ctx.binary_module = ctx.compiler


    ctf = ctx.translator
    ctf.input_schema = ctx.input_schema
    ctf.result_schema = ctx.result_schema
    ctf.binary_module = ctx.binary_module
    ctx.result = ctx.translator

    ctx.kwargs = Cell()
    ctf.kwargs = ctx.kwargs

    ctx.print_result = lambda result_: print("RESULT", result_)
    ctx.print_result.result_ = ctx.result

    # 2: Set up the values for a specific example
    ctx.cppcode = set_resource("test.cpp")
    ctx.cppcode.celltype = "text"

    ctx.tf = lambda a,b: a + b
    ctx.tf.a = 0 #example-based programming, to fill the schema
    ctx.tf.b = 0
    ctx.tf.with_result = True
    ctx.tf.result = 0.0 #example-based programming, to fill the schema

    ctf = ctx.compiler
    ctf.compiled_code = ctx.cppcode
    ctf.language = "cpp"
    ctf.main_module = {
        "objects": {
            "code": {
                "target": "debug",
            },
        },
        "link_options" : ["-lm"],
    }
    ctf.compiler_verbose = True

    #connect the schema's; just the values, for now... #TODO: pins!
    ctx.input_schema = ctx.tf.inp.schema.value
    ctx.result_schema = ctx.tf.result.schema._dict #TODO: solve inconsistency...

    ctx.translator.pins = ctx.tf._get_tf().tf._transformer_params ### convoluted way to access, but nothing we can do
    ctx.kwargs = {"a": 2, "b": 3}

    ctx.equilibrate()
    print(dict(ctx.translator.pins.value.items()))    
else:
    stdlib.compiled_transformer = ctx
