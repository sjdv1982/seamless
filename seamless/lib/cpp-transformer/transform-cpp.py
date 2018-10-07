import hashlib
import importlib
import sys, os
import tempfile
from cffi import FFI

cppcode = cppcode.data #Silk
header = header.data #Silk

name = __fullname__
if name.startswith("translated."):
    name = name[len("translated."):]
name = name.replace(".", "_")
name += "_" + hashlib.md5(header.encode()+cppcode.encode()).hexdigest()
module_name= "_seamless_" + name

import numpy.distutils.core #should enable Fortran support in sources

try:
    mydir = os.getcwd()
    os.chdir(tempfile.gettempdir())
    try:
        ffi = importlib.import_module(module_name)
    except ImportError as imp:
        ffibuilder = FFI()
        ffibuilder.cdef(header)
        #ffibuilder.set_source(module_name, cppcode, source_extension='.cpp')
        main_file = module_name + "_main.cpp"
        #main_file = module_name + "_main.f90"
        ffibuilder.set_source(module_name, header, sources=[main_file])
        with open(main_file, "w") as f:
            f.write(cppcode)
        try:
            ffibuilder.compile(verbose=True)
        except Exception as exc:
            raise exc from None
        ffi = importlib.import_module(module_name)
finally:
    os.chdir(mydir)

##############################################

def build_arg(prop, prop_jtype):
    v = globals()[prop]
    if prop_jtype in ("number", "integer"):
        pass
    elif prop_jtype == "str":
        v = ffi.new("char[]", v)
    else:
        raise NotImplementedError(prop_jtype)
    return v

args = []
input_jtype = input_schema["type"]
if input_jtype == "array":
    raise NotImplementedError
elif input_jtype == "object":
    input_props = input_schema["properties"]
else:
    input_props = {"input": input_schema}

order = input_schema.get("order", [])
for prop in sorted(input_props.keys()):
    if prop not in order:
        order.append(prop)
for propnr, prop in enumerate(order):
    propschema = input_props[prop]
    prop_jtype = propschema["type"]
    arg = build_arg(prop, prop_jtype)
    args.append(arg)

result = ffi.lib.transform(*args)

sys.modules.pop(module_name, None)
sys.modules.pop(module_name + ".lib", None)
