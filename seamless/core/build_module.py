from copy import deepcopy
import json
import re
import shutil
import sys, os
import importlib
import tempfile
import pprint
import traceback
from types import ModuleType
from weakref import WeakKeyDictionary
from ..calculate_checksum import calculate_checksum, calculate_dict_checksum
from ..compiler.locks import dirlock
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

from ..pylru import lrucache
module_cache = lrucache(size=100)
module_definition_cache = WeakKeyDictionary()

class Package:
    def __init__(self, mapping):
        self.mapping = mapping

bootstrap_package_definition = None

def build_interpreted_module(
    full_module_name, module_definition, module_workspace,
    module_error_name, parent_module_name=None,
    *, module_debug_mounts
):
    from ..ipython import ipython2python, execute as execute_ipython
    global bootstrap_package_definition
    language = module_definition["language"]
    code = module_definition["code"]
    assert language in ("python", "ipython"), language
    if isinstance(code, dict):
        return build_interpreted_package(
            full_module_name, language, code, module_workspace,
            parent_module_name=parent_module_name,
            module_error_name=module_error_name,
            module_debug_mounts=module_debug_mounts
        )

    assert isinstance(code, str), type(code)    
    package_name = None
    filename = module_error_name + ".py"
    if module_debug_mounts is not None:
        if module_error_name in module_debug_mounts: # single-file modules
            filename = module_debug_mounts[module_error_name]["path"]
        else:
            module_path = module_error_name.split(".")
            if module_path[0] in module_debug_mounts: # multi-file modules
                dirname = module_debug_mounts[module_path[0]]["path"]
                filename = os.path.join(dirname, module_path[1]) + ".py"
    mod = ModuleType(full_module_name)
    if parent_module_name is not None:
        package_name = parent_module_name
        if package_name.endswith(".__init__"):
            package_name = package_name[:-len(".__init__")]
            module_definition_cache[mod] = bootstrap_package_definition
        else:
            pos = package_name.rfind(".")
            if pos > -1:
                package_name = package_name[:pos]        
        mod.__package__ = package_name
    else:
        bootstrap_package_definition = module_definition
    mod.__path__ = []
    namespace = mod.__dict__
    sysmodules = {}
    try:
        for ws_modname, ws_mod in module_workspace.items():
            ws_modname2 = ws_modname
            if ws_modname2.endswith(".__init__"):
                ws_modname2 = ws_modname2[:-len(".__init__")]
            sysmod = sys.modules.pop(ws_modname2, None)
            sysmodules[ws_modname2] = sysmod
            sys.modules[ws_modname2] = ws_mod
        if language == "ipython":
            code = ipython2python(code)
            execute_ipython(code, namespace)
        else:
            try:
                from .cached_compile import cached_compile
                code_obj = cached_compile(code, filename)
                exec(code_obj, namespace)
            except ModuleNotFoundError as exc:
                mname = module_error_name
                excstr = traceback.format_exception_only(type(exc), exc)
                excstr = "\n".join(excstr)
                raise Exception(mname + ": " + excstr) from None
    finally:
        for sysmodname, sysmod in sysmodules.items():
            if sysmod is None:
                sys.modules.pop(sysmodname, None)
            else:
                sys.modules[sysmodname] = sysmod
    return mod

def build_interpreted_package(
    full_module_name, language, package_definition, module_workspace,
    *, parent_module_name, module_error_name,
    module_debug_mounts
):
    global bootstrap_package_definition
    assert language == "python", language
    assert "__init__" in package_definition
    if parent_module_name is None:
        parent_module_name = full_module_name
        mod = ModuleType(full_module_name)
        module_workspace[full_module_name] = mod
        bootstrap_package_definition = package_definition        
    
    p = {}
    mapping = {}
    for k,v in package_definition.items():
        if k == "__name__":
            continue
        assert isinstance(k,str), k
        assert isinstance(v, dict)
        assert "code" in v, k
        assert isinstance(v["code"], str), k
        vv = v
        if v.get("dependencies"):
            vv = v.copy()
            v["dependencies-ORIGINAL"] = deepcopy(v["dependencies"])
            for depnr, dep in enumerate(v["dependencies"]):
                dep2 = parent_module_name + dep if dep[:1] == "." else dep
                if dep2 == "__init__":
                    dep2 = parent_module_name + "." + dep2
                vv["dependencies"][depnr] = dep2
        assert k[:2] != "..", k
        kk = parent_module_name + k if k[:1] == "." else k
        p[kk] = v
        k2 = k if k[:-1] == "." else "." + k
        modname = full_module_name + k2
        mapping[modname] = kk
    build_all_modules(
        p, module_workspace, 
        mtype="interpreted", 
        compilers=None, languages=None, # only for compiled modules
        parent_module_name=parent_module_name,
        module_error_name=module_error_name,
        module_debug_mounts=module_debug_mounts,
        internal_package_name=package_definition.get("__name__")
    )
    return Package(mapping)
    
def import_extension_module(curr_extension_dir, full_module_name, module_code, debug, source_files):        
    module_file = os.path.join(curr_extension_dir, full_module_name + ".so")
    with open(module_file, "wb") as f:
        f.write(module_code)
    if debug:
        module_dir = os.path.join(curr_extension_dir, full_module_name)
        os.makedirs(module_dir)
        for filename, data in source_files.items():
            fn = os.path.join(module_dir, filename)
            with open(fn, "w") as f:
                f.write(data)
    syspath_old = []
    syspath_old = sys.path[:]
    try:
        sys.path.append(curr_extension_dir)
        importlib.import_module(full_module_name)
        mod = sys.modules.pop(full_module_name)
        return mod
    finally:
        sys.path[:] = syspath_old
        if not debug:
            os.remove(module_file)

def _merge_objects(objects):
    result = {}
    n_merged = 0
    for objname, obj in objects.items():
        if obj["compile_mode"] in ("object", "archive"):
            obj_file = objname
            if obj["compile_mode"]  == "object":
                obj_file += ".o"
            else:
                obj_file += ".a"
            curr = deepcopy(obj)
            curr["code_dict"] = {
                objname + "." + obj["extension"]: obj["code"]
            }
            curr.pop("code")
            result[obj_file] = curr
        elif obj["compile_mode"] == "package":     
            for oname, o in result.items():
                if not oname.startswith("_PACKAGE__"):
                    continue
                if o["language"] == obj["language"] and o["compiler"] == obj["compiler"]:
                    pass
            else:
                curr = deepcopy(obj)
                curr.pop("code")
                n_merged += 1
                result["_PACKAGE__%d.a" % n_merged] = curr
                curr["code_dict"] = {}
            curr["code_dict"][objname + "." + obj["extension"]] = obj["code"]                    
    return result

from ..pylru import lrucache
_compilation_buffers = lrucache(size=1000)

def get_compiled_module_code(checksum):
    return _compilation_buffers.get(checksum, (None, None))

def build_compiled_module(full_module_name, original_checksum, checksum, module_definition, *, module_error_name):
    """ Don't add salt to the extension dir. Instead, use a global compilation lock
    
    # curr_extension_dir = os.path.join(SEAMLESS_EXTENSION_DIR, random.randbytes(8).hex())
    
    """
    import distutils.errors
    for trial in range(5):
        try:
            curr_extension_dir = SEAMLESS_EXTENSION_DIR
            build_dir = os.path.join(curr_extension_dir, full_module_name)
            with dirlock(curr_extension_dir) as dl:
                os.makedirs(curr_extension_dir,exist_ok=True)
                shutil.rmtree(build_dir,ignore_errors=True)
                module_code = None
                module_code_checksum, module_code = get_compiled_module_code(original_checksum)
                if module_code is None:
                    module_code_checksum = database.get_compile_result(checksum)
                    if module_code_checksum is not None:
                        module_code = get_buffer(module_code_checksum, remote=True)
                source_files = {}
                debug = (module_definition.get("target") == "debug")
                if module_code is None:
                    if _blocked:
                        raise Exception("Building compiled modules is blocked")
                    objects = module_definition["objects"]
                    objects = _merge_objects(objects)
                    binary_objects = {}
                    remaining_objects = {}
                    object_checksums = {}
                    for object_file, object_ in objects.items():
                        object_checksum = calculate_dict_checksum(object_)
                        binary_code = None
                        binary_code_checksum = database.get_compile_result(object_checksum)
                        if binary_code_checksum is None:
                            binary_code = get_buffer(binary_code_checksum, remote=True)
                        if binary_code is not None:
                            binary_objects[object_file] = binary_code
                        else:
                            remaining_objects[object_file] = object_
                        object_checksums[object_file] = object_checksum
                    if len(remaining_objects):                                       
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
                        for object_file, binary_code in new_binary_objects.items():
                            binary_objects[object_file] = binary_code
                            object_checksum = object_checksums[object_file]
                            binary_code_checksum = calculate_checksum(binary_code)
                            # Disable writing of compiled code for now
                            """
                            buffer_remote.write_buffer(binary_code_checksum, binary_code)
                            database.set_buffer_length(binary_code_checksum, len(binary_code))
                            database.set_compile_result(object_checksum, binary_code_checksum)
                            """
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
                    module_code_checksum = calculate_checksum(module_code)
                    _compilation_buffers[original_checksum] = module_code_checksum, module_code
                    # Disable writing of compiled code for now
                    """
                    buffer_remote.write_buffer(module_code_checksum, module_code)
                    database.set_buffer_length(module_code_checksum, len(module_code))
                    if not buffer_remote.can_write():
                        _compilation_buffers[original_checksum] = module_code_checksum, module_code
                    database.set_compile_result(checksum, module_code_checksum)
                    """
                mod = import_extension_module(curr_extension_dir, full_module_name, module_code, debug, source_files)
            return mod
        except (FileNotFoundError, BuildModuleError, distutils.errors.LinkError) as exc:
            print("COMPILATION FAILURE", trial+1, full_module_name, file=sys.stderr)
            traceback.print_exc()
            print("/COMPILATION FAILURE", trial+1, full_module_name, file=sys.stderr)
            shutil.rmtree(build_dir,ignore_errors=True)
        except Exception as exc:
            raise exc from None
    raise exc from None

def build_module(module_definition, module_workspace={}, *,
     compilers, languages, module_debug_mounts,
     module_error_name, mtype=None, parent_module_name=None,
    ):
    if mtype is None:
        mtype = module_definition["type"]
    else:
        assert module_definition.get("type", mtype) == mtype
    assert mtype in ("interpreted", "compiled"), mtype
    json.dumps(module_definition)
    module_definition2 = module_definition
    if mtype == "compiled":
        module_definition2 = module_definition.copy()
        module_definition2["@NAME"] = module_error_name
    checksum = calculate_dict_checksum(module_definition2)
    dependencies = module_definition.get("dependencies")
    full_module_name = "seamless_module_" + checksum.hex()
    if module_error_name is not None:
        full_module_name += "_" + module_error_name
    cached = False
    if module_debug_mounts is None:
        if full_module_name in module_cache:
            mod = module_cache[full_module_name]
            if isinstance(mod, Package):
                for k in mod.mapping:
                    if k in module_cache:
                        module_workspace[k] = module_cache[k]
                    else:
                        break
                else:
                    cached = True
            else:
                cached = True
    if not cached:
        if mtype == "interpreted":
            mod = build_interpreted_module(
                full_module_name, module_definition, module_workspace,
                parent_module_name=parent_module_name,
                module_error_name=module_error_name,
                module_debug_mounts=module_debug_mounts
            )
        elif mtype == "compiled":
            assert parent_module_name is None
            completed_module_definition = complete(module_definition, compilers, languages)
            completed_checksum = calculate_dict_checksum(completed_module_definition)
            mod = build_compiled_module(
              full_module_name, checksum,
              completed_checksum, completed_module_definition,
              module_error_name=module_error_name
            )
        if not dependencies:
            module_cache[full_module_name] = mod
        if parent_module_name is None:
            module_definition_cache[mod] = module_definition
    return full_module_name, mod

def build_all_modules(
    modules_to_build, module_workspace, *, 
    compilers, languages,
    module_debug_mounts,
    mtype=None, parent_module_name=None,
    module_error_name=None,
    internal_package_name=None    
):
    global bootstrap_package_definition
    try:
        full_module_names = {}
        all_modules = sorted(list(modules_to_build.keys()))
        while len(modules_to_build):
            modules_to_build_new = {}
            for modname, module_def in modules_to_build.items():
                deps = module_def.get("dependencies", [])
                for dep in deps:
                    if dep not in module_workspace:
                        modules_to_build_new[modname] = module_def
                        break
                else:
                    modname2 = None
                    if parent_module_name is not None:
                        modname2 = parent_module_name + "." + modname
                    modname3 = modname
                    if module_error_name is not None:
                        modname3 = module_error_name + "." + modname
                    modname4 = modname
                    if parent_module_name is not None:
                        modname4 = modname2
                    mod = build_module(
                        module_def, module_workspace, 
                        compilers=compilers, languages=languages,
                        mtype=mtype, parent_module_name=modname2,
                        module_error_name=modname3,
                        module_debug_mounts=module_debug_mounts
                    )
                    assert mod is not None, modname
                    full_module_names[modname] = mod[0]
                    module_workspace[modname4] = mod[1]
                    if internal_package_name is not None:
                        pos = modname4.find(".")
                        modname5 = internal_package_name
                        if pos > -1:
                            modname5 += modname4[pos:]
                        module_workspace[modname5] = mod[1]
            
            if len(modules_to_build_new) == len(modules_to_build):
                deps = {}
                for modname, module_def in modules_to_build.items():
                    cdeps = module_def.get("dependencies")
                    if cdeps:
                        deps[modname] = cdeps
                depstr = pprint.pformat(deps)
                raise Exception("""Circular or unfulfilled dependencies:

{}

All modules: {}
""".format(depstr, all_modules))     
            
        
            modules_to_build = modules_to_build_new
                    
        return full_module_names
    finally:
        if parent_module_name is None:
            bootstrap_package_definition = None

def bootstrap():
    """Returns a module definition for the Python module/package that calls bootstrap()
    
If it is a normal file (module) or directory (package), 
the files are loaded and converted to a Seamless module definition.
If the Python module/package has been built (or is being built) by Seamless (with build_module),
the module definition is simply returned.
"""
    import inspect, sys, os
    if bootstrap_package_definition is not None:
        return bootstrap_package_definition
    package_namespace = inspect.currentframe().f_back.f_globals
    package = package_namespace.get("__package__")
    if package not in (None, "", "transformer", "reactor", "macro"):        
        mod = sys.modules[package]
        try:
            mod.__file__
        except AttributeError as exc:            
            if mod in module_definition_cache:
                return module_definition_cache[mod]
            else:
                raise exc from None
        package_dir = os.path.dirname(os.path.abspath(mod.__file__))
        return "TODO: LOAD PACKAGE DIR'{}'".format(package_dir)
    else:
        try:
            module_file = package_namespace["__file__"]
            return "TODO: LOAD MODULE FILE '{}'".format(module_file)
        except KeyError as exc:
            name = package_namespace["__name__"]
            if name in sys.modules:
                mod = sys.modules[name]
                if mod in module_definition_cache:
                    return module_definition_cache[mod]
            raise exc from None

_blocked = False

def block():
    global _blocked
    _blocked = True

def unblock():
    global _blocked
    _blocked = False

from .cache import buffer_remote    
from .cache.database_client import database
from .protocol.get_buffer import get_buffer