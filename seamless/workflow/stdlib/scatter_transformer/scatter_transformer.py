"""A "virtual transformer" that scatters one input (list or dict) 
and gathers the result. Much like a scattered_value CommandLineTool in CWL.
- language: transformer language
- code: transformer source code
- result: output cell to connect to
- scatter: name of the inputpin to scatter
- celltypes: dict of all celltypes of all inputpins and the result pin
- **inputpins: captures all other arguments

Limitation: celltypes in a separate dict (ugly). No schema/example support.
"""

import seamless

seamless.delegate(False)

from seamless.workflow.core.context import Macro
from seamless.workflow.core.transformer import Transformer
from seamless.workflow import Context, Cell
import sys

# 1: Setup context

ctx = Context()


def macro_code(
    ctx, tf_graph, scattered_input, scattered_input_name, celltypes, **kwargs
):
    for k in kwargs:
        assert k.startswith("PIN_"), k
    if isinstance(scattered_input, list):
        keys = range(1, len(scattered_input) + 1)
        values = scattered_input
        hash_pattern = {"!": "#"}
    elif isinstance(scattered_input, dict):
        for k in scattered_input:
            if not isinstance(k, str):
                raise TypeError(
                    "Pin '{}' to scatter is a dict with non-string key '{}'".format(
                        scattered_input_name, k
                    )
                )
        keys = scattered_input.keys()
        values = scattered_input.values()
        hash_pattern = {"*": "#"}
    else:
        raise TypeError(
            "Pin '{}' to scatter must be a list or dict, not '{}'".format(
                scattered_input_name, type(scattered_input)
            )
        )

    pseudo_connections = []
    ctx.result = cell("mixed", hash_pattern=hash_pattern)

    ctx.sc_data = cell("mixed", hash_pattern=hash_pattern)
    ctx.sc_buffer = cell("mixed", hash_pattern=hash_pattern)
    ctx.sc = StructuredCell(
        data=ctx.sc_data,
        buffer=ctx.sc_buffer,
        inchannels=[(k,) for k in keys],
        outchannels=[()],
        hash_pattern=hash_pattern,
    )

    for key, value in zip(keys, values):
        hc = HighLevelContext(tf_graph)

        subctx = "subctx_%s" % key
        setattr(ctx, subctx, hc)

        for k in kwargs:
            hc[k].set(kwargs[k])
        hc[scattered_input_name].set(value)
        con = [".." + scattered_input_name], ["ctx", subctx, "tf", scattered_input_name]
        pseudo_connections.append(con)

        tf_result_name = "TRANSFORMER_RESULT_" + str(key)
        c = cell(celltypes.get("result", "mixed"))
        setattr(ctx, tf_result_name, c)
        hc.result.connect(c)
        c.connect(ctx.sc.inchannels[(key,)])

        con = ["ctx", subctx, "result"], ["..result"]
        pseudo_connections.append(con)

    ctx.sc.outchannels[()].connect(ctx.result)
    ctx._pseudo_connections = pseudo_connections


def constructor(ctx, libctx, language, code, result, scatter, inputpins, celltypes):
    ctx.code = Cell("text")
    ctx.code.set(code)
    ctx.result = Cell()

    if scatter not in inputpins:
        raise AttributeError("Pin '{}' to scatter does not exist".format(scatter))
    scattered_input = inputpins[scatter]

    if scattered_input[0] == "value":
        # Simple case (scattered input as value)
        scattered_value = scattered_input[1]

        if isinstance(scattered_value, list):
            keys = range(1, len(scattered_value) + 1)
            values = scattered_value
        elif isinstance(scattered_value, dict):
            for k in scattered_value:
                if not isinstance(k, str):
                    raise TypeError(
                        "Pin '{}' to scatter is a dict with non-string key '{}'".format(
                            scatter, k
                        )
                    )
            keys = scattered_value.keys()
            values = scattered_value.values()
        else:
            raise TypeError(
                "Pin '{}' to scatter must be a list or dict, not '{}'".format(
                    scatter, type(scattered_value)
                )
            )

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
                if pin_name in celltypes:
                    getattr(tf.pins, pin_name).celltype = celltypes[pin_name]
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
    elif scattered_input[0] == "cell":
        # Complex case (scattered input as cell)
        scattered_cell = scattered_input[1]

        tf_ctx = Context()
        tf_ctx[scatter] = Cell(celltype=celltypes.get(scatter, "mixed"))
        tf = tf_ctx.tf = Transformer()
        tf[scatter] = tf_ctx[scatter]
        getattr(tf.pins, scatter).celltype = celltypes.get(scatter, "mixed")
        tf.code = code
        for pin_name in inputpins:
            if pin_name == scatter:
                continue
            pin_type, pin_value = inputpins[pin_name]
            pin_name2 = "PIN_" + pin_name
            if pin_type == "value":
                tf[pin_name] = pin_value
            elif pin_type == "cell":
                tf_ctx[pin_name2] = Cell(celltype=celltypes.get(pin_name, "mixed"))
                tf[pin_name] = tf_ctx[pin_name2]
            getattr(tf.pins, pin_name).celltype = celltypes.get(pin_name, "mixed")

        tf_ctx.result = Cell(celltype=celltypes.get("result", "mixed"))
        tf_ctx.result = tf.result
        tf_ctx.compute()
        tf_graph = tf_ctx.get_graph()

        ctx.m = Macro()
        ctx.m.code = libctx.macro_code.value
        ctx.m.tf_graph = tf_graph
        ctx.scattered_input = Cell(scattered_cell.celltype)
        ctx.m.scattered_input = ctx.scattered_input
        scattered_cell.connect(ctx.scattered_input)
        ctx.m.scattered_input_name = scatter
        ctx.m.celltypes = celltypes

        for pin_name in inputpins:
            if pin_name == scatter:
                continue
            pin_type, pin_cell = inputpins[pin_name]
            pin_name2 = "PIN_" + pin_name
            if pin_type == "cell":
                ctx[pin_name2] = Cell(celltype=celltypes.get(pin_name, "mixed"))
                pin_cell.connect(ctx[pin_name2])
                setattr(ctx.m, pin_name2, ctx[pin_name2])

        ctx.m.pins.result = {"io": "output", "celltype": "mixed"}
        ctx.result = ctx.m.result

    else:
        raise TypeError(scattered_input[0])
    result.connect_from(ctx.result)


ctx.macro_code = Cell("code").set(macro_code)
ctx.constructor_code = Cell("code").set(constructor)
ctx.constructor_params = {
    "language": {"type": "value", "io": "input", "default": "python"},
    "code": "value",
    "result": {"type": "cell", "io": "output"},
    "scatter": "value",
    "celltypes": {"type": "value", "io": "input", "default": {}},
    "inputpins": {"type": "kwargs", "io": "input"},
}

ctx.compute()

# 2: obtain graph and zip

graph = ctx.get_graph()
zip = ctx.get_zip()

# 3: Package the contexts in a library

from seamless.workflow.highlevel.library import LibraryContainer

mylib = LibraryContainer("mylib")
mylib.scatter_transformer = ctx
mylib.scatter_transformer.constructor = ctx.constructor_code.value
mylib.scatter_transformer.params = ctx.constructor_params.value

# 4: Run test example

ctx = Context()
ctx.include(mylib.scatter_transformer)


def add(a, b):
    return a + b


ctx.tf = ctx.lib.scatter_transformer()
ctx.tf.code = add
ctx.tf.scatter = "a"
ctx.tf.a = [10, 20, 30]
ctx.b = 1000
ctx.tf.b = ctx.b
ctx.result = ctx.tf.result
ctx.compute()
print(ctx.tf.status)
if ctx.tf.status != "Status: OK":
    print(ctx.tf.exception)
print(ctx.result.value)

ctx.tf.a = {"x": 100.1, "y": 200.1, "z": 300.1}
ctx.tf.celltypes = {"a": "int"}
ctx.b = -1000
ctx.compute()
print(ctx.tf.status)
if ctx.tf.status != "Status: OK":
    print(ctx.tf.exception)
print(ctx.result.value)

ctx.a = {"p": 1000, "q": 2000, "r": 3000}
ctx.tf.a = ctx.a
ctx.b = 1
ctx.compute()
print(ctx.tf.status)
if ctx.tf.status != "Status: OK":
    print(ctx.tf.exception)
    # print(ctx.tf.ctx.m.exception)
    # print(ctx.tf.ctx.m.ctx.subctx_p.tf.exception)
print(ctx.result.value)


ctx.a = {"pp": 100, "qq": 200, "rr": 300}
import asyncio

asyncio.get_event_loop().run_until_complete(asyncio.sleep(2))  # no re-translation
print(ctx.tf.status)
if ctx.tf.status != "Status: OK":
    print(ctx.tf.exception)
    # print(ctx.tf.ctx.m.exception)
    # print(ctx.tf.ctx.m.ctx.subctx_p.tf.exception)
print(ctx.result.value)

if not ctx.result.value.unsilk:
    sys.exit()

# 5: Save graph and zip

import os, json

currdir = os.path.dirname(os.path.abspath(__file__))
graph_filename = os.path.join(currdir, "../scatter_transformer.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename = os.path.join(currdir, "../scatter_transformer.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)
print("Graph saved")
