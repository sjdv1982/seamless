"""
Switch: connect an input cell to one output cell, dynamically chosen from a dict
Select: dynamically connect one input cell, dynamically chosen from a dict, to one output cell
"""

from seamless.highlevel import Context, Cell
import sys

# 1: Setup contexts

ctx_switch = Context()
ctx_select = Context()
"""
 Only "parameter" pins end up in the macro code
 However, ctx.input will be connected to
  and ctx.foo will be connected from, where "foo" is any value in the cell dict
"""
def switch_func(ctx, celltype, selected, options):
    assert selected in options, (selected, options)
    ctx.input = cell(celltype)
    selected_output = cell(celltype)
    setattr(ctx, selected, selected_output)
    ctx.input.connect(selected_output)

def select_func1(ctx, celltype, selected, options):
    assert selected in options, (selected, options)
    ctx.output = cell(celltype)
    selected_input = cell(celltype)
    setattr(ctx, selected, selected_input)
    selected_input.connect(ctx.output)

def select_func2(ctx, celltype, input_hash_pattern, input_value, selected):
    ctx.output = cell(celltype)
    if not isinstance(input_value, dict):
        raise TypeError("input cell must contain a dict")

    if input_hash_pattern == "":
        input_hash_pattern = None

    if input_hash_pattern is None or input_hash_pattern == "#":
        ctx.selected_input = cell("mixed")
    elif input_hash_pattern == "##":
        ctx.selected_input = cell("bytes")
    else:
        raise ValueError(input_hash_pattern)
    ctx.selected_input.connect(ctx.output)

    selected_input = input_value.get(selected)
    if selected_input is None:
        return
    
    if input_hash_pattern is None:
        ctx.selected_input.set(selected_input)
    else:
        ctx.selected_input.set_checksum(selected_input)
    
def constructor_switch(ctx, libctx, celltype, input, selected, outputs):
    import json
    ctx.input = Cell(celltype)
    input.connect(ctx.input)
    ctx.selected = Cell("str")
    selected.connect(ctx.selected)

    macro_pins = {
        "celltype": {
            "io": "parameter", 
            "celltype": "str",
        },
        "input": {
            "io": "input", 
            "celltype": celltype,
        },
        "selected": {
            "io": "parameter", 
            "celltype": "str",
        },
        "options": {
            "io": "parameter", 
            "celltype": "plain",
        }
    }

    """
    Create one macro output pin per cell in the outputs dict
    This will populate the ctx passed to switch_func with output cells
     that can be connected to
    """
    options = []
    for output_name in outputs:
        if not isinstance(output_name, str):
            output_name = json.loads(json.dumps(output_name))
        assert isinstance(output_name, str), output_name
        if output_name in macro_pins or output_name == "switch_macro":
            msg = "You cannot switch to a cell under the selector '{}'"
            raise Exception(msg.format(output_name))
        options.append(output_name)
        pin = {
            "io": "output",
            "celltype": celltype
        }
        macro_pins[output_name] = pin
    ctx.switch_macro = Macro(pins=macro_pins)
    ctx.switch_macro.code = libctx.switch_code.value
    ctx.switch_macro.celltype = celltype
    ctx.switch_macro.input = ctx.input
    ctx.switch_macro.selected = ctx.selected
    ctx.switch_macro.options = options

    for output_name in outputs:
        macro_pin = getattr(ctx.switch_macro, output_name)
        output_cell = Cell(celltype)
        setattr(ctx, output_name, output_cell)
        setattr(ctx, output_name, macro_pin)
        outputs[output_name].connect_from(output_cell)

def constructor_select(ctx, libctx, celltype, input, inputs, selected, output):
    if input is None and inputs is None:
        raise TypeError("You must define 'input' or 'inputs'")
    if input is not None and inputs is not None:
        raise TypeError("You must define 'input' or 'inputs', not both")
    ctx.output = Cell(celltype)
    output.connect_from(ctx.output)
    ctx.selected = Cell("str")
    selected.connect(ctx.selected)

    # Version 1: a celldict of input cells
    if inputs is not None: 
        """
        Create one macro input pin per cell in the inputs dict
        This will populate the ctx passed to select_func with input cells
        that can be connected to
        """
        macro1_pins = {
            "celltype": {
                "io": "parameter", 
                "celltype": "str",
            },
            "output": {
                "io": "output", 
                "celltype": celltype,
            },
            "selected": {
                "io": "parameter", 
                "celltype": "str",
            },
            "options": {
                "io": "parameter", 
                "celltype": "plain",
            }
        }

        options = []
        for input_name in inputs:
            if not isinstance(input_name, str):
                input_name = json.loads(json.dumps(input_name))
            assert isinstance(input_name, str), input_name
            if input_name in macro1_pins or input_name == "select_macro1":
                msg = "You cannot select from a cell under the selector '{}'"
                raise Exception(msg.format(input_name))
            options.append(input_name)
            pin = {
                "io": "input",
                "celltype": celltype
            }
            macro1_pins[input_name] = pin
        ctx.select_macro1 = Macro(pins=macro1_pins)
        ctx.select_macro1.code = libctx.select_code1.value
        ctx.select_macro1.celltype = celltype
        ctx.select_macro1.selected = ctx.selected
        ctx.select_macro1.options = options

        for input_name in inputs:
            input_cell = Cell(celltype)
            setattr(ctx, input_name, input_cell)
            setattr(ctx.select_macro1, input_name, input_cell)
            inputs[input_name].connect(input_cell)
        
        ctx.output = ctx.select_macro1.output
    else:
        # Version 2: a structured input cell
        macro2_pins = {
            "celltype": {
                "io": "parameter", 
                "celltype": "str",
            },
            "output": {
                "io": "output", 
                "celltype": celltype,
            },
            "input_hash_pattern": {
                "io": "parameter", 
                "celltype": "plain",
            },
            "input_value": {
                "io": "parameter", 
                "celltype": "plain",
            },
            "selected": {
                "io": "parameter", 
                "celltype": "str",
            }
        }

        if input.celltype != "structured":
            raise TypeError("'input' must be a structured cell")

        ctx.select_macro2 = Macro(pins=macro2_pins)
        ctx.select_macro2.code = libctx.select_code2.value
        ctx.select_macro2.celltype = celltype
        ctx.input = Cell()        
        input.connect(ctx.input)
        if input.hash_pattern is None:
            ctx.select_macro2.input_value = ctx.input
            ctx.select_macro2.input_hash_pattern = ""  # macro params must be defined!
        else:
            ctx.input.hash_pattern = input.hash_pattern
            ctx.input_checksum = Cell("checksum")
            ctx.input_checksum = ctx.input
            ctx.input_deep = Cell("plain")
            ctx.input_deep = ctx.input_checksum
            ctx.select_macro2.input_value = ctx.input_deep
            ctx.select_macro2.input_hash_pattern = input.hash_pattern["*"]
        ctx.select_macro2.selected = ctx.selected

        ctx.output = ctx.select_macro2.output

ctx_switch.switch_code = Cell("code")
ctx_switch.switch_code = switch_func
ctx_switch.constructor_code = Cell("code")
ctx_switch.constructor_code = constructor_switch
ctx_switch.constructor_params = {
    "celltype": "value",
    "input": {
        "type": "cell",
        "io": "input"
    },
    "selected": {
        "type": "cell",
        "io": "input"
    },
    "outputs": {
        "type": "celldict",
        "io": "output"
    },
}
ctx_switch.compute()

ctx_select.select_code1 = Cell("code")
ctx_select.select_code1 = select_func1
ctx_select.select_code2 = Cell("code")
ctx_select.select_code2 = select_func2
ctx_select.constructor_code = Cell("code")
ctx_select.constructor_code = constructor_select
ctx_select.constructor_params = {
    "celltype": "value",
    "output": {
        "type": "cell",
        "io": "output"
    },
    "selected": {
        "type": "cell",
        "io": "input"
    },
    "inputs": {
        "type": "celldict",
        "io": "input",
        "must_be_defined": False,
    },
    "input": {
        "type": "cell",
        "io": "input",
        "must_be_defined": False,
    },
}
ctx_select.compute()

# 2: obtain graph and zip

graph_switch = ctx_switch.get_graph()
zip_switch = ctx_switch.get_zip()
graph_select = ctx_select.get_graph()
zip_select = ctx_select.get_zip()

# 3: Package the contexts in a library

from seamless.highlevel.library import LibraryContainer
mylib = LibraryContainer("mylib")
mylib.switch = ctx_switch
mylib.switch.constructor = ctx_switch.constructor_code.value
mylib.switch.params = ctx_switch.constructor_params.value
mylib.select = ctx_select
mylib.select.constructor = ctx_select.constructor_code.value
mylib.select.params = ctx_select.constructor_params.value

# 4: Run test example

ctx2 = Context()
ctx2.include(mylib.switch)
ctx2.include(mylib.select)
ctx2.a = 10.0
ctx2.a1 = Cell("float")
ctx2.a2 = Cell("float")
ctx2.a3 = Cell("float")
ctx2.f1 = 2.0
ctx2.f2 = 3.0
ctx2.f3 = 4.0

def add(a,b):
    return a + b
def sub(a,b):
    return a - b
def mul(a,b):
    return a * b

ctx2.op1 = add
ctx2.op1.a = ctx2.a1
ctx2.op1.b = ctx2.f1
ctx2.r1 = ctx2.op1

ctx2.op2 = sub
ctx2.op2.a = ctx2.a2
ctx2.op2.b = ctx2.f2
ctx2.r2 = ctx2.op2

ctx2.op3 = mul
ctx2.op3.a = ctx2.a3
ctx2.op3.b = ctx2.f3
ctx2.r3 = ctx2.op3

adict = {
    "path1": ctx2.a1,
    "path2": ctx2.a2,
    "path3": ctx2.a3,
}
rdict = {
    "path1": ctx2.r1,
    "path2": ctx2.r2,
    "path3": ctx2.r3,
}
ctx2.selected = "path1"

ctx2.switch = ctx2.lib.switch(
    celltype="float",
    input=ctx2.a,
    selected=ctx2.selected,
    outputs=adict,
)
ctx2.compute()
ctx2.output = Cell("float")
ctx2.select = ctx2.lib.select(
    celltype="float",
    inputs=rdict,
    selected=ctx2.selected,
    output=ctx2.output,
)
ctx2.compute()

print(ctx2.output.value)
print(ctx2.a.value, ctx2.a1.value, ctx2.a2.value, ctx2.a3.value)
print(ctx2.a1.status, ctx2.a2.status, ctx2.a3.status)
#print(ctx2.switch.ctx.switch_macro._get_mctx().path1.status)
#print(ctx2.switch.ctx.path2._get_cell().upstream().status)
#print(ctx2.switch.ctx.path2.status)
#print(ctx2.a2._get_cell().status)
#print(ctx2.a2._get_cell().upstream().status)
print(ctx2.r1.value, ctx2.r2.value, ctx2.r3.value)
print()

ctx2.selected = "path2"
print(ctx2._needs_translation)
ctx2.compute()
print(ctx2.output.value)
print(ctx2.a.value, ctx2.a1.value, ctx2.a2.value, ctx2.a3.value)
print(ctx2.a1.status, ctx2.a2.status, ctx2.a3.status)
print(ctx2.r1.value, ctx2.r2.value, ctx2.r3.value)
print()

ctx2.selected = "path3"
print(ctx2._needs_translation)
ctx2.compute()
print(ctx2.output.value)
print(ctx2.a.value, ctx2.a1.value, ctx2.a2.value, ctx2.a3.value)
print(ctx2.a1.status, ctx2.a2.status, ctx2.a3.status)
print(ctx2.r1.value, ctx2.r2.value, ctx2.r3.value)
print()

if ctx2.output.value is None:
    sys.exit()

del ctx2.select
ctx2.translate()
ctx2.output = None

ctx2.r = Cell()
ctx2.r["path1!"] = ctx2.r1
ctx2.r["path2!"] = ctx2.r2
ctx2.r["path3!"] = ctx2.r3
ctx2.compute()

ctx2.selected2 = Cell("str")
ctx2.select = ctx2.lib.select(
    celltype="float",
    input=ctx2.r,
    selected=ctx2.selected2,
    output=ctx2.output,
)
ctx2.compute()
ctx2.selected2 = "path3!"
print(ctx2._needs_translation)
ctx2.compute()
print(ctx2.output.value)

ctx2.selected = "path1"
ctx2.selected2 = "path1!"
print(ctx2._needs_translation)
ctx2.compute()
print(ctx2.output.value)
print()

ctx2.r.hash_pattern = {"*": "#"}
ctx2.compute()
print(ctx2.output.value)
ctx2.selected = "path2"
ctx2.selected2 = "path2!"
print(ctx2._needs_translation)
ctx2.compute()
print(ctx2.output.value)
print()

if ctx2.output.value is None:
    sys.exit()

# 5: Save graph and zip

print("Save graph and zip")
import os, json
currdir=os.path.dirname(os.path.abspath(__file__))
graph_switch_filename=os.path.join(currdir,"../switch.seamless")
json.dump(graph_switch, open(graph_switch_filename, "w"), sort_keys=True, indent=2)
graph_select_filename=os.path.join(currdir,"../select.seamless")
json.dump(graph_select, open(graph_select_filename, "w"), sort_keys=True, indent=2)

zip_switch_filename=os.path.join(currdir,"../switch.zip")
with open(zip_switch_filename, "bw") as f:
    f.write(zip_switch)
zip_select_filename=os.path.join(currdir,"../select.zip")
with open(zip_select_filename, "bw") as f:
    f.write(zip_select)
