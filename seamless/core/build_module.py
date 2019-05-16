import json
import os
import tempfile
from weakref import WeakValueDictionary
from types import ModuleType
from ..get_hash import get_dict_hash
from ..compiler.locks import locks, locklock
from ..compiler import compile, complete
from ..compiler.build_extension import build_extension_cffi
from ..ipython import execute as ipython_execute

SEAMLESS_EXTENSION_DIR = os.path.join(tempfile.gettempdir(), "seamless-extensions")
#  Here Seamless will write the compiled Python module .so files before importing

COMPILE_VERBOSE = True

module_cache = WeakValueDictionary()

def build_interpreted_module(full_module_name, module_definition):
    language = module_definition["language"]
    code = module_definition["code"]
    assert language in ("python", "ipython"), language
    assert isinstance(code, str), type(code)
    mod = ModuleType(full_module_name)
    namespace = mod.__dict__
    if language == "ipython":
        ipython_execute(code, namespace)
    else:
        exec(code, namespace)
    return mod

def import_extension_module(full_module_name, module_code):
    with locklock:
        if not os.path.exists(SEAMLESS_EXTENSION_DIR):
            os.makedirs(SEAMLESS_EXTENSION_DIR)
        module_file = os.path.join(SEAMLESS_EXTENSION_DIR, full_module_name)
        with open(module_file, "wb") as f:
            f.write(extension_code)
        syspath_old = []
        syspath_old = sys.path[:]
        try:
            sys.path.append(SEAMLESS_EXTENSION_DIR)
            importlib.import_module(full_module_name)
            mod = sys.modules.pop(full_module_name)
            return mod
        finally:
            sys.path[:] = syspath_old

def build_compiled_module(full_module_name, checksum, module_definition):
    from .cache.redis_client import redis_caches, redis_sinks
    mchecksum = b"python-ext-" + checksum
    module_code = redis_caches.get_compile_result(mchecksum)
    if module_code is None:
        objects = module_definition["objects"]
        binary_objects = {}
        remaining_objects = {}
        object_checksums = {}
        for objectname, object_ in objects.items():
            object_checksum = get_dict_hash(object_, hex=True)
            binary_code = redis_caches.get_compile_result(object_checksum)
            if binary_code is not None:
                binary_objects[objectname] = binary_code
                object_checksums[objectname] = object_checksum
            else:
                remaining_objects[objectname] = object_
        if len(remaining_objects):
            with locklock:
                build_dir = os.path.join(SEAMLESS_EXTENSION_DIR, full_module_name)
                if not os.path.exists(build_dir):
                    os.makedirs(build_dir)
            new_binary_objects = compile(
              remaining_objects, build_dir, compiler_verbose=COMPILE_VERBOSE
            )
            for objectname, binary_code in new_binary_objects.items():                
                binary_objects[objectname] = binary_code
                object_checksum = object_checksums[objectname]
                redis_sinks.set_compile_result(object_checksum, binary_code)
        link_options = module_definition["link_options"]
        target = module_definition["target"]
        header = module_definition["public_header"]
        assert header["language"] == "c", header["language"]
        c_header = header["code"]
        module_code = build_extension_cffi(
          binary_objects, 
          target, 
          c_header, 
          link_options, 
          compiler_verbose=COMPILE_VERBOSE
        )
        redis_sinks.set_compile_result(mchecksum, module_code)
    mod = build_compiled_module(full_module_name, module_code)
    return mod

def build_module(module_definition):
    mtype = module_definition["type"]
    assert mtype in ("interpreted", "compiled"), mtype
    json.dumps(module_definition)    
    checksum = get_dict_hash(module_definition, hex=True)
    full_module_name = "seamless_module_" + checksum
    if full_module_name not in module_cache:
        if mtype == "interpreted":
            mod = build_interpreted_module(full_module_name, module_definition)
        elif mtype == "compiled":
            completed_module_definition = complete(module_definition)
            completed_checksum = get_dict_hash(completed_module_definition, hex=True)
            mod = build_compiled_module(
              full_module_name, completed_checksum, completed_module_definition
            )
        module_cache[full_module_name] = mod
    else:
        mod = module_cache[full_module_name]
    return full_module_name, mod