import numpy as np
from seamless.highlevel import Context, Cell
from seamless.lib import set_resource

ctx = Context()
ctx.tf = lambda a,b: a + b
ctx.tf.a = 0 #example-based programming, to fill the schema
ctx.tf.b = 0

ctx.a = 2
ctx.a.celltype = "json" #int!
ctx.b = 3
ctx.b.celltype = "json" #int!
ctx.tf.a = ctx.a
ctx.tf.b = ctx.b
ctx.tf.with_result = True
ctx.tf.result = 0 #example-based programming, to fill the schema

#connect the schema's; just the values, for now...
ctx.input_schema = ctx.tf.inp.schema.value
ctx.result_schema = ctx.tf.result.schema._dict #TODO: solve inconsistency...

ctx.mount("/tmp/seamless-test", persistent=False) #TODO: persistent=False (does not delete atm)

ctx.gen_header = lambda input_schema, result_schema: None
ctx.gen_header.input_schema = ctx.input_schema
ctx.gen_header.result_schema = ctx.result_schema
print(ctx.gen_header.input_schema.value)

ctx.translate()

ctx.gen_header.code = set_resource("gen_header.py")
ctx.header = ctx.gen_header
ctx.header.celltype = "text"
ctx.print_header = lambda header: print("HEADER", header)
ctx.print_header.header = ctx.header

ctx.cppcode = set_resource("test.cpp")
ctx.cppcode.celltype = "text"

ctx.cpp_transformer = lambda header, cppcode, input_schema, result_schema, a, b: None
ctf = ctx.cpp_transformer
ctf.header = ctx.header
ctf.cppcode = ctx.cppcode
ctf.input_schema = ctx.input_schema
ctf.result_schema = ctx.result_schema
ctf.a = ctx.a
ctf.b = ctx.b
ctx.cpp_transformer.code = set_resource("transform-cpp.py")

ctx.translate()

ctx.result = ctx.cpp_transformer
ctx.result.celltype = "text"

ctx.print_result = lambda result_: print("RESULT", result_)
ctx.print_result.result_ = ctx.result

ctx.translate()
