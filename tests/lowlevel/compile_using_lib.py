"""
Final test for compiled transformers, using stdlib.compiled_transformer
"""

from seamless.core import context, cell, transformer, macro, libcell, macro_mode_on
from seamless.core import StructuredCell
from seamless.core import library
from copy import deepcopy

# 1: set up example data
with macro_mode_on():
    ctx = context(toplevel=True)

    # 1a. Setup of StructuredCells
    ctx.inp_struc = context(name="inp_struc",context=ctx)
    ctx.inp_struc.storage = cell("text")
    ctx.inp_struc.form = cell("json")
    ctx.inp_struc.data = cell("mixed",
        form_cell = ctx.inp_struc.form,
        storage_cell = ctx.inp_struc.storage,
    )
    ctx.inp_struc.schema = cell("json")
    ctx.inp = StructuredCell(
        "inp",
        ctx.inp_struc.data,
        storage = ctx.inp_struc.storage,
        form = ctx.inp_struc.form,
        schema = ctx.inp_struc.schema,
        buffer = None,
        inchannels = [],
        outchannels = [()]
    )
    ctx.result_struc = context(name="result_struc",context=ctx)
    ctx.result_struc.storage = cell("text")
    ctx.result_struc.form = cell("json")
    ctx.result_struc.data = cell("mixed",
        form_cell = ctx.result_struc.form,
        storage_cell = ctx.result_struc.storage,
    )
    ctx.result_struc.schema = cell("json")
    ctx.result = StructuredCell(
        "result",
        ctx.result_struc.data,
        storage = ctx.result_struc.storage,
        form = ctx.result_struc.form,
        schema = ctx.result_struc.schema,
        buffer = None,
        inchannels = [()],
        outchannels = [()]
    )
    ctf = ctx.tf = context(name="tf",context=ctx)

    # 1b. Example values
    inp = ctx.inp.handle
    inp.a = 2
    inp.b = 3
    result = ctx.result.handle
    result.set(0.0)

    ctx.compiled_code = cell("text").set(
"""extern "C" double transform(int a, int b) {
    return a + b;
}"""
    )
    ctx.language = cell("text").set("cpp")
    ctx.main_module = cell("json").set({})
    ctx.compiler_verbose = cell("json").set(True)
    ctx.pins = cell("json").set({
        'a': {'io': 'input', 'transfer_mode': 'copy', 'access_mode': 'object'},
        'b': {'io': 'input', 'transfer_mode': 'copy', 'access_mode': 'object'},
        'result': "output"
    })


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

    ctf.compiler_code = libcell(".compiler.code")
    ctf.compiler_params = libcell(".compiler_params")
    ctf.compiler = transformer(ctf.compiler_params.value)
    ctf.compiler_code.connect(ctf.compiler.code)

    ctf.translator_code = libcell(".translator.code")
    ctf.translator_params = libcell(".translator_params")
    ctf.translator = transformer(ctf.translator_params.value)
    ctf.translator_code.connect(ctf.translator.code)
    ctf.translator.result_name.cell().set("result")
    ctf.translator.input_name.cell().set("input")

# 3: set up connections to library
with macro_mode_on():
    #3a: between example and library
    ctx.pins.connect(ctf.translator.pins)
    ctx.result.connect_inchannel(ctf.translator.translator_result_, ())
    ctx.inp.connect_outchannel((), ctf.translator.kwargs)
    ctx.inp_struc.schema.connect(ctf.gen_header.input_schema)
    ctx.result_struc.schema.connect(ctf.gen_header.result_schema)
    ctx.inp_struc.schema.connect(ctf.translator.input_schema)
    ctx.result_struc.schema.connect(ctf.translator.result_schema)

    #3b: among library cells
    ctx.header = cell("text")
    ctf.gen_header.result.connect(ctx.header)
    ctx.header.connect(ctf.compiler.header)

    ctx.language.connect(ctf.compiler.lang)
    ctx.compiled_code.connect(ctf.compiler.compiled_code)
    ctx.main_module.connect(ctf.compiler.main_module)
    ctx.compiler_verbose.connect(ctf.compiler.compiler_verbose)

    ctx.binary_module_storage = cell("text")
    ctx.binary_module_form = cell("json")
    ctx.binary_module = cell(
        "mixed",
        storage_cell = ctx.binary_module_storage,
        form_cell = ctx.binary_module_form,
    )
    ctf.compiler.result.connect(ctx.binary_module)

    ctx.binary_module.connect(ctf.translator.binary_module)

ctx.equilibrate()
print(ctx.pins.value)
print(ctx.inp_struc.schema.value)
print(ctx.result_struc.schema.value)
print(ctx.header.value)
print(ctx.binary_module.value)
print(ctx.result.value)

inp.a.set(10)
ctx.equilibrate()
print(ctx.result.value)

inp.q.set(100.0)
pins = deepcopy(ctx.pins.value)
pins.update({
    'q': {'io': 'input', 'transfer_mode': 'copy', 'access_mode': 'object'},
})
ctx.pins.set(pins)
ctx.compiled_code.set(
"""extern "C" double transform(int a, int b, double q) {
return a + b + q;
}""")

ctx.compiler_verbose.set(False)
ctx.equilibrate()
print(ctx.inp_struc.schema.value)
print(ctx.result.value)
print(ctx.status())

ctx.compiled_code.set(
"""extern "C" double transform(int a, int b, double q) {
return a + b - q;
}""")
ctx.equilibrate()
print(ctx.result.value)
print(ctx.status())
