"""NextFlow-style channels
These work like NextFlow value channels.
Since Seamless is purely functional,
there is no such thing as NextFlow queue channels

Work in progress!
"""

import seamless

seamless.delegate(0)

from seamless.workflow.core.transformer import Transformer
from seamless.workflow import Context, Cell
from seamless.workflow.highlevel.library import LibraryContainer
from silk.Silk import Silk

mylib = LibraryContainer("mylib")

ctx0 = Context()


def fromPath(self, pattern, is_text):
    # Warning: loads everything into memory! Make version that takes a cell...
    import glob

    if not hasattr(self, "state"):
        self.state = {}
    operators = getattr(self.state, "operators", [])
    if len(operators) or hasattr(self.state, "startvalue"):
        raise ValueError("fromPath must be the first operator")
    filenames = glob.glob(pattern)
    if not len(filenames):
        raise ValueError("No files found")
    if is_text:
        mode = "r"
    else:
        mode = "rb"
    startvalue = {}
    for filename in filenames:
        with open(filename, mode) as f:
            content = f.read()
            startvalue[filename] = content
    self.state.startvalue = startvalue
    self.state.is_dict = True
    return self.libinstance


def fromList(self, content):
    if not hasattr(self, "state"):
        self.state = {}
    operators = getattr(self.state, "operators", [])
    if len(operators) or hasattr(self.state, "startvalue"):
        raise ValueError("fromList must be the first operator")
    if not isinstance(content, list):
        raise ValueError(content)
    self.state.startvalue = content
    self.state.is_dict = False
    return self.libinstance


def _get_source(self, function):
    from seamless.workflow.highlevel import parse_function_code
    from seamless.checksum.cached_compile import analyze_code

    source, _, _ = parse_function_code(function)
    mode, func_name = analyze_code(source, "filter")
    if mode == "lambda":
        code = "LAMBDA = " + source
        func_name = "LAMBDA"
    elif mode == "function":
        code = source
    else:
        raise ValueError(mode)
    return code, func_name


def filter(self, function):
    code, func_name = self.PRIVATE_get_source(function)
    code += "\n\n"

    if not hasattr(self, "state"):
        self.state = {}
    if not hasattr(self.state, "startvalue"):
        raise ValueError("'filter' cannot be the first operator")
    is_dict = True
    if not getattr(self.state, "is_dict"):
        is_dict = False

    if is_dict:
        code += (
            """
keep = {}        
for k,v in channel_contents.items():
    if %s(k,v):
        keep[k] = v
result = keep"""
            % func_name
        )
    else:
        code += (
            """
keep = []        
for it in channel_contents:
    if %s(it):
        keep.append(it)
result = keep"""
            % func_name
        )

    if not hasattr(self.state, "operators"):
        self.state.operators = []
    operator = ("filter", code)
    self.state.operators.append(operator)
    return self.libinstance


def first(self, function):
    code, func_name = self.PRIVATE_get_source(function)
    code += "\n\n"

    if not hasattr(self, "state"):
        self.state = {}
    if not hasattr(self.state, "startvalue"):
        raise ValueError("'first' cannot be the first operator")
    is_dict = True
    if not getattr(self.state, "is_dict"):
        is_dict = False

    if is_dict:
        code += (
            """
result = None        
for k,v in channel_contents.items():
    if %s(k,v):
        result = (k,v)
        break"""
            % func_name
        )
    else:
        code += (
            """
result = None
for it in channel_contents:
    if %s(it):
        result = it
        break"""
            % func_name
        )

    if not hasattr(self.state, "operators"):
        self.state.operators = []
    operator = ("first", code)
    self.state.is_dict = False
    self.state.is_scalar = True
    self.state.operators.append(operator)
    return self.libinstance


api_schema = {}
s = Silk(schema=api_schema)
s.fromPath = fromPath
s.fromList = fromList
s.filter = filter
s.first = first
s.PRIVATE_get_source = _get_source


def constructor(ctx, libctx, result, state={}, **kw):
    ctx.result = Cell("mixed")
    if state is None:
        return
    startvalue = state.get("startvalue")
    if startvalue is not None:
        ctx.startvalue = Cell("mixed").set(startvalue)
        channel_contents = ctx.startvalue
        for step, operator in enumerate(state.get("operators", [])):
            opname, op_params = operator
            subctxname = "step%d_%s" % (step + 1, opname)
            ctx[subctxname] = Context()
            subctx = ctx[subctxname]
            if opname in ("filter", "first"):
                subctx.tf = Transformer()
                subctx.tf.code = op_params
                subctx.tf.channel_contents = channel_contents
                subctx.result = subctx.tf
                subctx.result.celltype = "mixed"
                channel_contents = subctx.result
            else:
                raise NotImplementedError(opname)
        ctx.result = channel_contents
    result.connect_from(ctx.result)


parameters = {
    "state": {
        "io": "input",
        "type": "value",
    },
    "result": {"io": "output", "type": "cell"},
    "kw": {"io": "input", "type": "kwargs"},
}


mylib.channel = ctx0
mylib.channel.constructor = constructor
mylib.channel.params = parameters
mylib.channel.api_schema = api_schema


ctx = Context()
ctx.include(mylib.channel)


def filter_code(key, value):
    import os

    return os.path.splitext(key)[1] == ""


ctx.filter_code = Cell("code").set(filter_code)
ctx.inst = ctx.lib.channel().fromPath("./*", is_text=True).filter(filter_code)
ctx.result = ctx.inst.result
ctx.result.celltype = "plain"
ctx.compute()

print(ctx.result.value)

ctx.inst.first(lambda k, v: k == "./b")
ctx.compute()

print(ctx.result.value)
print(ctx.inst.ctx.step2_first.tf.status)
print(ctx.inst.ctx.step2_first.tf.exception)

"""
    if not hasattr(self, "kw"):
        self.kw = {}
    n = 0
    while 1:
        n += 1
        c = "cell%d" % n
        if c not in self.kw:
            break
    self.kw[c] = function.path
"""

# 2: obtain graph and zip

ctx0.constructor_code = Cell("code").set(constructor)
ctx0.constructor_params = parameters
ctx0.api_schema = api_schema
ctx0.compute()

graph = ctx0.get_graph()
zip = ctx0.get_zip()

# 5: Save graph and zip

import os, json

currdir = os.path.dirname(os.path.abspath(__file__))
graph_filename = os.path.join(currdir, "../channel.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename = os.path.join(currdir, "../channel.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)
print("Graph saved")
