from seamless.core.transformation import SeamlessStreamTransformationError
from silk import Silk
import numpy as np
import operator, functools
import sys
import wurlitzer

ffi = module.ffi

ARRAYS = [] #a list of Numpy arrays whose references must be kept alive
FFI_OBJS = [] #a list of FFI objects whose references must be kept alive

def get_dtype(type, unsigned, bytesize): #adapted from _form_to_dtype_scalar
    if type == "string":
        return np.dtype('S1')
    if type == "integer":
        result = "="
        if unsigned:
            result += "u"
        else:
            result += "i"
        if bytesize is not None:
            result += str(bytesize)
    elif type == "number":
        result = "="
        result += "f"
        if bytesize is not None:
            result += str(bytesize)
    else:
        raise TypeError(type)
    return np.dtype(result)

json_to_c = {
    "integer": "int",
    ("integer", 1): "int8_t",
    ("integer", 2): "int16_t",
    ("integer", 4): "int32_t",
    ("integer", 8): "int64_t",
    "number": "double",
    ("number", 4): "float",
    ("number", 8): "double",
    "boolean": "bool",
    "string": "char",
}

def gen_basic_type(schema):
    warnings = []
    has_form = "form" in schema
    if has_form:
        form = schema["form"]
    else:
        form = {}
    type = schema["type"]
    ctype = json_to_c[type]
    result = ctype
    if type in ("integer", "number"):
        if not has_form or "bytesize" not in form:
            result = ctype
        else:
            result = json_to_c[type, form["bytesize"]]
    if type == "integer":
        if form.get("unsigned"):
            if result.endswith("_t"):
                result = "u" + result
            else:
                result = "unsigned " +  result
    return result

#TODO: share with gen-header code
def gen_struct_name(name):
    def capitalize(subname):
        return "".join([subsubname.capitalize() for subsubname in subname.split("_")])
    if isinstance(name, str):
        name = (name,)
    return "".join([capitalize(subname) for subname in name]) + "Struct"

def build_array_struct(name, arr, with_strides):
    array_struct_name = gen_struct_name(name)
    array_struct = ffi.new(array_struct_name + " *")
    array_struct.shape[0:len(arr.shape)] = arr.shape[:]
    if with_strides:
        array_struct.strides[0:len(arr.strides)] = arr.strides[:]
    if isinstance(arr, Silk):
        arr = arr.data
    ptr = ffi.from_buffer(arr)
    array_struct.data = ffi.cast(ffi.typeof(array_struct.data), ptr)
    return array_struct

def build_result_array_struct(name, schema):
    array_struct_name = gen_struct_name(name)
    shape = schema["form"]["shape"]
    try:
        type = schema["items"]["type"]
    except KeyError:
        type = schema["items"]["form"]["type"]
    unsigned = schema["items"]["form"].get("unsigned", False)
    bytesize = schema["items"]["form"].get("bytesize")
    dtype = get_dtype(type, unsigned, bytesize)
    array_struct = ffi.new(array_struct_name + " *")
    array_struct.shape[0:len(shape)] = shape[:]
    arr = np.zeros(shape=shape,dtype=dtype)
    ARRAYS.append(arr)
    arr_ptr = ffi.from_buffer(arr)
    array_struct.data = ffi.cast(ffi.typeof(array_struct.data), arr_ptr)
    return array_struct

def build_result_struct(schema):
    global result_struct
    result_struct_name = gen_struct_name(result_name)
    result_struct = ffi.new(result_struct_name+" *")
    props = schema["properties"]
    for propname, propschema in props.items():
        proptype = propschema["type"]
        if proptype == "object":
            raise NotImplementedError #nested result struct
        elif proptype == "array":
            full_propname = (result_name, propname)
            form = propschema.get("form", {})
            result_array_struct = build_result_array_struct(full_propname, propschema)
            FFI_OBJS.append(result_array_struct)
            setattr(result_struct, propname, result_array_struct)
        else:
            pass
    return result_struct

def build_result_array(schema):
    global result_struct
    result_struct_name = gen_struct_name(result_name)
    shape = schema["form"]["shape"]
    for dim in shape:
        if dim <= 0:
            raise ValueError("Result shape {} contains non-positive numbers".format(shape))
    try:
        type = schema["items"]["type"]
    except KeyError:
        type = schema["items"]["form"]["type"]
    unsigned = schema["items"]["form"].get("unsigned", False)
    bytesize = schema["items"]["form"].get("bytesize")
    dtype = get_dtype(type, unsigned, bytesize)
    result_struct = ffi.new(result_struct_name + " *")
    result_struct.shape[0:len(shape)] = shape[:]
    arr = np.zeros(shape=shape,dtype=dtype)
    ARRAYS.append(arr)
    arr_ptr = ffi.from_buffer(arr)
    result_struct.data = ffi.cast(ffi.typeof(result_struct.data), arr_ptr)
    return result_struct

def unpack_result_array_struct(array_struct, schema):
    ""
    shape = schema["form"]["shape"]
    try:
        type = schema["items"]["type"]
    except KeyError:
        type = schema["items"]["form"]["type"]
    unsigned = schema["items"]["form"].get("unsigned", False)
    bytesize = schema["items"]["form"].get("bytesize")
    dtype = get_dtype(type, unsigned, bytesize)
    shape = list(array_struct.shape)
    nbytes = functools.reduce(operator.mul, shape, 1) * dtype.itemsize
    """
    buf = ffi.buffer(array_struct.data, nbytes)
    arr = np.frombuffer(buf,dtype=dtype).reshape(shape)
    # In theory, no copy needs to be made, but in practice, still...
    arr = arr.copy()
    """
    #instead, just pop off the array...
    arr = ARRAYS.pop(0)
    assert arr.dtype == dtype
    assert arr.shape == tuple(shape), (arr.shape, shape)
    assert arr.nbytes == nbytes
    return arr

def unpack_result_struct(result_struct, schema):
    result_dict = {}
    props = schema["properties"]
    for propname, propschema in props.items():
        proptype = propschema["type"]
        if proptype == "object":
            raise NotImplementedError #nested result struct
        elif proptype == "array":
            result_array_struct = getattr(result_struct, propname)
            result_dict[propname] = unpack_result_array_struct(result_array_struct, propschema)
        else:
            result_dict[propname] = getattr(result_struct, propname)
    return result_dict

### Start

input_pins = []
for k,v in pins.items():
    vv = v if isinstance(v, str) else v["io"]
    if vv == "input":
        input_pins.append(k)
args = []
assert input_schema["type"] == "object"
input_props = input_schema["properties"]

for pin in input_pins:
    if pin not in input_props:
        raise TypeError("Missing schema for input pin .%s" % pin)

order = input_schema.get("order", [])
for prop in sorted(input_props.keys()):
    if prop not in order:
        order.append(prop)
for propnr, prop in enumerate(order):
    value = kwargs[prop]
    propschema = input_props[prop]
    proptype = propschema["type"]
    if proptype == "object":
        raise NotImplementedError #binary struct in input
    elif proptype == "array":
        form = propschema.get("form", {})
        with_strides = ("contiguous" not in form or not form["contiguous"])
        array_struct = build_array_struct(prop, value, with_strides)
        args.append(array_struct)
    else:
        args.append(value)

if result_schema["type"] == "object":
    result_arg = build_result_struct(result_schema)
elif result_schema["type"] == "array":
    result_arg = build_result_array(result_schema)
else:
    result_arg_name = gen_basic_type(result_schema)
    result_arg = ffi.new(result_arg_name+" *")
args.append(result_arg)

def run():
    error_code = module.lib.transform(*args)
    if error_code != 0:
        return error_code, None
    if result_schema["type"] == "object":
        result = unpack_result_struct(args[-1], result_schema)
    elif result_schema["type"] == "array":
        result = unpack_result_array_struct(args[-1], result_schema)
    else:
        result = args[-1][0]
    return 0, result

with wurlitzer.pipes() as (stdout, stderr):
    error_code, result = run()
sys.stderr.write(stderr.read())
sys.stdout.write(stdout.read())
ARRAYS.clear()
if error_code != 0:
    raise SeamlessStreamTransformationError("Compiled transformer returned non-zero value: {}".format(error_code))