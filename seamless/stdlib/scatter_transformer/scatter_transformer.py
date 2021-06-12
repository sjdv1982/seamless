"""A "virtual transformer" that scatters one input (list or dict) 
and gathers the result. Much like a scattered CommandLineTool in CWL.
- language: transformer language
- code: transformer source code
- result: output cell to connect to
- scatter: name of the inputpin to scatter
- **inputpins: captures all other arguments

Limitation: scattered inputpin must be supplied as value, not as cell.
As with any LibInstance value,
  any changes in the value will require re-translation
=> the number of scatterings is static, not dynamic.

TODO: break this limitation using highlevel.Macro + core.HighLevelContext, like stdlib.map does.
"""

from seamless.core.transformer import Transformer
from seamless.highlevel import Context, Cell
import sys

# 1: Setup context

ctx = Context()

def constructor(
    ctx, libctx,
    language, code, result, scatter, inputpins
):
    ctx.code = Cell("text")
    ctx.code.set(code)
    ctx.result = Cell()

    if scatter not in inputpins:
        raise AttributeError("Pin '{}' to scatter does not exist".format(scatter))
    scattered_pin = inputpins[scatter]
    if scattered_pin[0] == "cell":
        raise NotImplementedError("For now, the scattered pin must be a value, not a cell")
    scattered = scattered_pin[1]

    if isinstance(scattered, list):
        keys = range(1,len(scattered)+1)
        values = scattered
    elif isinstance(scattered, dict):
        for k in scattered:
            if not isinstance(k, str):
                raise TypeError("Pin '{}' to scatter is a dict with non-string key '{}'".format(scatter, k))
        keys = scattered.keys()
        values = scattered.values()
    else:
        raise TypeError("Pin '{}' to scatter must be a list or dict, not '{}'".format(scatter, type(scattered)))

    for pin_name in inputpins:
        if pin_name == scatter:
            continue
        pin_type, pin_cell = inputpins[pin_name]
        if pin_type != "cell":
            continue
        ctx[pin_name] = Cell(pin_cell.celltype)
        pin_cell.connect(ctx[pin_name])

    for key, value in zip(keys, values):
        tf_name = "TRANSFORMER_" + str(key)
        tf = ctx[tf_name] = Transformer()
        tf.language = language
        tf.code = ctx.code
        tf[scatter] = value
        for pin_name in inputpins:
            if pin_name == scatter:
                continue
            pin_type, pin_content = inputpins[pin_name]
            if pin_type == "value":
                tf[pin_name] = pin_content
            else:
                tf[pin_name] = ctx[pin_name]
        tf_result_name = "TRANSFORMER_RESULT_" + str(key)
        ctx[tf_result_name] = tf.result
        ctx.result[key] = ctx[tf_result_name]
    result.connect_from(ctx.result)

ctx.constructor_code = Cell("code").set(constructor)
ctx.constructor_params = {
    "language": {
        "type": "value",
        "io": "input",
        "default": "python"
    },
    "code": "value",
    "result": {
        "type": "cell",
        "io": "output"
    },
    "scatter": "value",
    "inputpins": {
        "type": "kwargs",
        "io": "input"
    },
}

ctx.compute()

# 2: obtain graph and zip

graph = ctx.get_graph()
zip = ctx.get_zip()

# 3: Package the contexts in a library

from seamless.highlevel.library import LibraryContainer
mylib = LibraryContainer("mylib")
mylib.scatter_transformer = ctx
mylib.scatter_transformer.constructor = ctx.constructor_code.value
mylib.scatter_transformer.params = ctx.constructor_params.value

# 4: Run test example

ctx = Context()
ctx.include(mylib.scatter_transformer)

def add(a,b):
    return a+b
ctx.tf = ctx.lib.scatter_transformer()
ctx.tf.code = add
ctx.tf.scatter = "a"
ctx.tf.a = [10, 20, 30]
ctx.b = 1000
ctx.tf.b = ctx.b
ctx.result = ctx.tf.result
ctx.compute()
print(ctx.tf.exception)
print(ctx.tf.status)
print(ctx.result.value)
ctx.tf.a = {"x": 100, "y": 200, "z": 300}
ctx.b = -1000
ctx.compute()
print(ctx.tf.exception)
print(ctx.tf.status)
print(ctx.result.value)

if not ctx.result.value.unsilk:
    sys.exit()

# 5: Save graph and zip

import os, json
currdir=os.path.dirname(os.path.abspath(__file__))
graph_filename=os.path.join(currdir,"../scatter_transformer.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename=os.path.join(currdir,"../scatter_transformer.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)
print("Graph saved")
