import json
import sys, os
import importlib
import tempfile
import pprint
from weakref import WeakValueDictionary
from types import ModuleType
from ..get_hash import get_dict_hash
from ..compiler.locks import locks, locklock
from ..compiler import compile, complete
from ..compiler.build_extension import build_extension_cffi

from concurrent.futures import ProcessPoolExecutor

class BuildModuleError(Exception):
    pass

remote_build_model_servers = []

SEAMLESS_EXTENSION_DIR = os.path.join(tempfile.gettempdir(), "seamless-extensions")
#  Here Seamless will write the compiled Python module .so files before importing

COMPILE_VERBOSE = True
CFFI_VERBOSE = False

module_cache = WeakValueDictionary()

def build_interpreted_module(full_module_name, module_definition, module_workspace):
    from ..ipython import ipython2python, execute as execute_ipython
    language = module_definition["language"]
    code = module_definition["code"]
    assert language in ("python", "ipython"), language
    assert isinstance(code, str), type(code)
    mod = ModuleType(full_module_name)
    mod.__path__ = []
    namespace = mod.__dict__
    sysmodules = {}
    try:
        for ws_modname, ws_mod in module_workspace.items():
            sysmod = sys.modules.pop(ws_modname, None)
            sysmodules[ws_modname] = sysmod
            sys.modules[ws_modname] = ws_mod
        if language == "ipython":
            code = ipython2python(code)
            execute_ipython(code, namespace)
        else:
            exec(code, namespace)
    finally:
        for sysmodname, sysmod in sysmodules.items():
            if sysmod is None:
                sys.modules.pop(sysmodname, None)
            else:
                sys.modules[sysmodname] = sysmod
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

def build_compiled_module(full_module_name, checksum, module_definition):
    from .cache.database_client import database_cache, database_sink
    mchecksum = b"python-ext-" + checksum
    module_code = database_cache.get_compile_result(mchecksum)
    source_files = {}
    debug = (module_definition.get("target") == "debug")
    if module_code is None:
        objects = module_definition["objects"]
        binary_objects = {}
        remaining_objects = {}
        object_checksums = {}
        for objectname, object_ in objects.items():
            object_checksum = get_dict_hash(object_)
            binary_code = database_cache.get_compile_result(object_checksum)
            if binary_code is not None:
                binary_objects[objectname] = binary_code
            else:
                remaining_objects[objectname] = object_
            object_checksums[objectname] = object_checksum
        if len(remaining_objects):
            build_dir = os.path.join(SEAMLESS_EXTENSION_DIR, full_module_name)               
            success, new_binary_objects, source_files, stderr = compile(
              remaining_objects, build_dir,
              compiler_verbose=module_definition.get(
                "compiler_verbose", COMPILE_VERBOSE
              ),
              build_dir_may_exist=debug
            )
            if not success:
                raise BuildModuleError(stderr)
            else:
                if len(stderr):
                    print(stderr)  # TODO: log this, but it is not obvious where
            for objectname, binary_code in new_binary_objects.items():
                binary_objects[objectname] = binary_code
                object_checksum = object_checksums[objectname]
                database_sink.set_compile_result(object_checksum, binary_code)
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
          compiler_verbose=module_definition.get(
            "compiler_verbose", CFFI_VERBOSE
          )
        )
        database_sink.set_compile_result(mchecksum, module_code)
    mod = import_extension_module(full_module_name, module_code, debug, source_files)
    return mod

def build_module(module_definition, module_workspace={}):
    mtype = module_definition["type"]
    assert mtype in ("interpreted", "compiled"), mtype
    json.dumps(module_definition)
    checksum = get_dict_hash(module_definition)
    full_module_name = "seamless_module_" + checksum.hex()
    if full_module_name not in module_cache:
        if mtype == "interpreted":
            mod = build_interpreted_module(full_module_name, module_definition, module_workspace)
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

async def build_module_async(module_definition, module_workspace={}):
    """
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as executor:
        full_module_name, mod = await loop.run_in_executor(
            executor,
            build_module,
            module_definition
        )
    """
    full_module_name, mod = build_module(module_definition, module_workspace)
    return full_module_name, mod

async def build_all_modules(modules_to_build):
    module_workspace = {} 
    all_modules = list(modules_to_build.keys())
    while len(modules_to_build):
        modules_to_build_new = {}
        for pinname, module_def in modules_to_build.items():
            deps = module_def.get("dependencies", [])
            for dep in deps:
                if dep not in module_workspace:
                    modules_to_build_new[pinname] = module_def
                    break
            else:
                mod = await build_module_async(module_def, module_workspace)
                assert mod is not None, pinname
                module_workspace[pinname] = mod[1]
        
        if len(modules_to_build_new) == len(modules_to_build):
            deps = {}
            for pinname, module_def in modules_to_build.items():
                cdeps = module_def.get("dependencies")
                if cdeps:
                    deps[pinname] = cdeps
            depstr = pprint.pformat(deps)
            raise Exception("""Circular or unfulfilled dependencies:

{}

All modules: {}
""".format(depstr, all_modules))     
            
        
        modules_to_build = modules_to_build_new
                
    return module_workspace