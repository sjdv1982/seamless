"""
Final test for compiled transformers, using stdlib.compiled_transformer
"""

from seamless.core import context, cell, transformer, macro, libcell, macro_mode_on
from seamless.core import StructuredCell
from seamless.core import library
from copy import deepcopy

DEBUG = True # Run compiled transformer in debugging mode (attach using gdb)

# 1: set up example data
with macro_mode_on():
    ctx = context(toplevel=True)

    # 1a. Setup of StructuredCells
    ctx.inp_struc = context()
    ctx.inp_struc.data = cell("mixed")
    ctx.inp_struc.schema = cell("plain")
    ctx.inp = StructuredCell(
        "inp",
        ctx.inp_struc.data,
        schema = ctx.inp_struc.schema,
        buffer = None,
        plain = True,
        inchannels = [],
        outchannels = [()]
    )

    ctx.result_struc = context()
    ctx.result_struc.data = cell("mixed")    
    ctx.result_struc.schema = cell("plain")
    ctx.result = StructuredCell(
        "result",
        ctx.result_struc.data,
        schema = ctx.result_struc.schema,
        buffer = None,
        plain = True,
        inchannels = [()],
        outchannels = [()]
    )
    ctf = ctx.tf = context()

    ctx.compiled_code = cell("text").set(
"""extern "C" double transform(int a, int b) {
    return a + b;
}"""
    )
    ctx.language = cell("text").set("cpp")
    ctx.main_module = cell("plain").set({})
    ctx.pins = cell("plain").set({
        'a': {'io': 'input', 'transfer_mode': 'copy', 'access_mode': 'object'},
        'b': {'io': 'input', 'transfer_mode': 'copy', 'access_mode': 'object'},
        'result': "output"
    })
    ctx.inputpins = cell("plain").set(["a", "b"])

# 1b. Example values
inp = ctx.inp.example
inp.set({})
inp.a = 0
inp.b = 0
result = ctx.result.example
result.set(0.0)

inp = ctx.inp.handle
inp.set({})
inp.a = 2
inp.b = 3

# Just to register the "compiled_transformer" lib
from seamless.lib.compiled_transformer import compiled_transformer as _

libdict = library._lib["compiled_transformer"]
libcells = [k for k in libdict.keys() if k.find("_STRUC") == -1]
print(libcells)

# 2: set up library
with macro_mode_on(), library.bind("compiled_transformer"):
    ctf.gen_header_code = libcell(".gen_header.code")
    ctf.gen_header_params = libcell(".gen_header_params")
    ctf.gen_header = transformer(ctf.gen_header_params.value)
    ctf.gen_header_code.connect(ctf.gen_header.code)
    ctf.gen_header.result_name.cell().set("result")
    ctf.gen_header.input_name.cell().set("input")

    ctf.integrator_code = libcell(".integrator.code")
    ctf.integrator_params = libcell(".integrator_params")
    ctf.integrator = transformer(ctf.integrator_params.value)
    ctf.integrator.debug_.cell().set(DEBUG)
    ctf.integrator_code.connect(ctf.integrator.code)

    ctf.translator_code = libcell(".translator.code")
    ctf.translator_params = libcell(".translator_params")
    ctf.translator = transformer(ctf.translator_params.value)
    ctf.translator_code.connect(ctf.translator.code)
    ctf.translator.result_name.cell().set("result")
    ctf.translator.input_name.cell().set("input")

    ctf.translator.debug = DEBUG

# 3: set up connections to library
with macro_mode_on():
    #3a: between example and library
    ctx.pins.connect(ctf.translator.pins)
    ctf.translator.translator_result_.connect(ctx.result.inchannels[()])
    ctx.inp.outchannels[()].connect(ctf.translator.kwargs)
    ctx.inputpins.connect(ctf.gen_header.inputpins)
    ctx.inp_struc.schema.connect(ctf.gen_header.input_schema)
    ctx.result_struc.schema.connect(ctf.gen_header.result_schema)
    ctx.inp_struc.schema.connect(ctf.translator.input_schema)
    ctx.result_struc.schema.connect(ctf.translator.result_schema)

    #3b: among library cells
    ctx.header = cell("text")
    ctf.gen_header.result.connect(ctx.header)
    ctx.header.connect(ctf.integrator.header)

    ctx.language.connect(ctf.integrator.lang)
    ctx.compiled_code.connect(ctf.integrator.compiled_code)
    ctx.main_module.connect(ctf.integrator.main_module)

    ctx.module = cell("mixed")
    ctf.integrator.result.connect(ctx.module)

    ctx.module.connect(ctf.translator.module)

print("START")
ctx.equilibrate()
print(ctx.pins.value)
print(ctx.inp_struc.schema.value)
print(ctx.result_struc.schema.value)
print(ctx.header.value)
print(ctx.module.value)
print(ctx.result.value)
print(ctx.status)
if DEBUG:
    import sys; sys.exit()

print("update")
inp = ctx.inp.handle
inp.a = 10
ctx.equilibrate()
print(ctx.result.value)

inp.q = 100
ctx.inp.example.q = 0.0
pins = deepcopy(ctx.pins.value)
pins.update({
    'q': {'io': 'input', 'transfer_mode': 'copy', 'access_mode': 'object'},
})
ctx.pins.set(pins)
ctx.compiled_code.set(
"""extern "C" double transform(int a, int b, double q) {
return a + b + q;
}""")

ctx.equilibrate()
print(ctx.inp_struc.schema.value)
print(ctx.result.value)
print(ctx.status)

ctx.compiled_code.set(
"""extern "C" double transform(int a, int b, double q) {
return a + b - q;
}""")
ctx.equilibrate()
print(ctx.result.value)
print(ctx.status)

ctx.compiled_code.set(
"""
#include <cstdio>
extern "C" double transform(int a, int b, double q) {
  printf("PRINTF transform: a=%d, b=%d, q=%.3f\\n", a, b, q);
  return 42;
}""")
ctx.equilibrate()
print(ctx.result.value)
print(ctx.status)
