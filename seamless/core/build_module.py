import json
import sys, os
import importlib
import tempfile
from weakref import WeakValueDictionary
from types import ModuleType
from ..get_hash import get_dict_hash
from ..compiler.locks import locks, locklock
from ..compiler import compile, complete
from ..compiler.build_extension import build_extension_cffi
from ..ipython import execute as ipython_execute

remote_build_model_servers = []

SEAMLESS_EXTENSION_DIR = os.path.join(tempfile.gettempdir(), "seamless-extensions")
#  Here Seamless will write the compiled Python module .so files before importing

COMPILE_VERBOSE = True
CFFI_VERBOSE = False

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

def import_extension_module(full_module_name, module_code, debug, source_files):
    with locklock:
        if not os.path.exists(SEAMLESS_EXTENSION_DIR):
            os.makedirs(SEAMLESS_EXTENSION_DIR)
        module_file = os.path.join(SEAMLESS_EXTENSION_DIR, full_module_name + ".so")
        with open(module_file, "wb") as f:
            f.write(module_code)
        if debug:
            module_dir = os.path.join(SEAMLESS_EXTENSION_DIR, full_module_name)
            os.makedirs(module_dir)
            for filename, data in source_files.items():
                fn = os.path.join(module_dir, filename)
                with open(fn, "w") as f:
                    f.write(data)
        syspath_old = []
        syspath_old = sys.path[:]
        try:
            sys.path.append(SEAMLESS_EXTENSION_DIR)
            importlib.import_module(full_module_name)
            mod = sys.modules.pop(full_module_name)
            return mod
        finally:
            sys.path[:] = syspath_old
            if not debug:
                os.remove(module_file)

def build_compiled_module_remote(full_module_name, checksum, module_definition):
    from ..core.run_multi_remote import run_multi_remote
    d_content = {
        "full_module_name": full_module_name,
        "checksum": checksum.hex(),
        "module_definition": module_definition,
    }
    content = json.dumps(d_content)
    future = run_multi_remote(remote_build_model_servers, content, origin=None)
    import asyncio
    asyncio.get_event_loop().run_until_complete(future)

def build_compiled_module(full_module_name, checksum, module_definition):
    from .cache.redis_client import redis_caches, redis_sinks
    mchecksum = b"python-ext-" + checksum
    module_code = redis_caches.get_compile_result(mchecksum)
    source_files = {}
    debug = False
    if module_code is None:
        build_compiled_module_remote(
          full_module_name, checksum, module_definition
        )
        module_code = redis_caches.get_compile_result(mchecksum)
        if module_code is not None:
            redis_sinks.set_compile_result(mchecksum, module_code)
    if module_code is None:
        objects = module_definition["objects"]
        binary_objects = {}
        remaining_objects = {}
        object_checksums = {}
        for objectname, object_ in objects.items():
            object_checksum = get_dict_hash(object_)
            binary_code = redis_caches.get_compile_result(object_checksum)
            if binary_code is not None:
                binary_objects[objectname] = binary_code                
            else:
                remaining_objects[objectname] = object_
            object_checksums[objectname] = object_checksum
        if len(remaining_objects):
            build_dir = os.path.join(SEAMLESS_EXTENSION_DIR, full_module_name)
            new_binary_objects, source_files = compile(
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
          full_module_name,
          binary_objects, 
          target, 
          c_header, 
          link_options, 
          compiler_verbose=CFFI_VERBOSE
        )
        redis_sinks.set_compile_result(mchecksum, module_code)
        debug = (module_definition.get("target") == "debug")
    mod = import_extension_module(full_module_name, module_code, debug, source_files)
    return mod

def build_module(module_definition):
    mtype = module_definition["type"]
    assert mtype in ("interpreted", "compiled"), mtype
    json.dumps(module_definition)    
    checksum = get_dict_hash(module_definition)
    full_module_name = "seamless_module_" + checksum.hex()
    if full_module_name not in module_cache:
        if mtype == "interpreted":
            mod = build_interpreted_module(full_module_name, module_definition)
        elif mtype == "compiled":
            completed_module_definition = complete(module_definition)
            completed_checksum = get_dict_hash(completed_module_definition)
            mod = build_compiled_module(
              full_module_name, completed_checksum, completed_module_definition
            )
        module_cache[full_module_name] = mod
    else:
        mod = module_cache[full_module_name]
    return full_module_name, mod