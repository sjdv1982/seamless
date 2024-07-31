from copy import deepcopy
from types import ModuleType
import sys
import pathlib
import ast

def get_pypackage_dependencies(pycode:str, package_name:str, is_init:bool):
    tree = ast.parse(pycode)
    deps = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for name in node.names:
                dep = name.name
                if package_name is None or not dep.startswith(package_name):
                    continue
                deps.add(dep)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if package_name is None or not node.module.startswith(package_name):
                    continue
            elif is_init and node.level == 1 and node.module is None:
                for name in node.names:
                    deps.add("." + name.name)
                continue
            dep = "." * node.level 
            if node.module is not None:
                dep += node.module
            deps.add(dep)
        else:
            continue
        
    return sorted(list(deps))


def pypackage_to_moduledict(pypackage_dirdict, internal_package_name=None):
    code = {}
    if internal_package_name is not None and len(internal_package_name):
        code["__name__"] = internal_package_name
    def analyze(d, prefix):
        for k,v in d.items():
            if isinstance(v, dict):
                new_prefix = prefix
                if len(new_prefix):
                    new_prefix += "."
                new_prefix += k
                analyze(v, new_prefix)
                continue
            assert isinstance(k, str), k
            if not k.endswith(".py"):
                continue
            f = k[:-3]
            if len(prefix):
                f = prefix + "." + f
            pycode = v
            is_init = f.endswith("__init__")
            deps0 = get_pypackage_dependencies(pycode, internal_package_name, is_init)
            deps = []
            ff = f.split(".")
            for dep in deps0:
                d = dep
                dots = 0
                dep2 = dep
                if not dep.startswith("."):
                    pos = len(ff)
                    if ff[-1] == "__init__":
                        pos -= 1
                    ind = dep.find(".")
                    if ind == -1:
                        if pos == 0:
                            continue
                        d = pos * "."
                    else:
                        d = pos * "." + dep[ind+1:]
                while d.startswith("."):
                    dots += 1
                    d = d[1:]
                if not len(d):
                    dep2 = ""
                    dpref = ".".join(ff[:-dots])
                    if len(dpref):
                        dep2 += "." + dpref + "." 
                    dep2 += "__init__"
                else:
                    dep2 = "."    
                    dpref = ".".join(ff[:-dots])
                    if len(dpref):
                        dep2 += dpref + "." 
                    dep2 += d
                if dep2 == f:
                    continue
                deps.append(dep2)
            deps = sorted(list(deps))
            item = {
                "language": "python",
                "code": pycode,
                "dependencies": deps,
            }
            code[f] = item
    dirdict = {}
    for k,v in pypackage_dirdict.items():
        if not isinstance(v, str):
            dirdict[k] = v
            continue
        kk = k.split("/")
        d = dirdict
        for p in kk[:-1]:
            if p not in d:
                d[p] = {}
            d = d[p]
        d[kk[-1]] = v
    analyze(dirdict, "")
    result = {
        "language": "python",
        "type": "interpreted",
        "code": code,
    }    
    return result

def _restore_dependencies(module_definition):
    dep_orig = module_definition.pop("dependencies-ORIGINAL", None)
    if dep_orig is not None:
        module_definition["dependencies"] = dep_orig
    code = module_definition["code"]
    if isinstance(code, dict):
        for sub_def in code.values():
            _restore_dependencies(sub_def)
    
def get_module_definition(module:ModuleType) -> dict[str]:
    from ...core.build_module import module_definition_cache
    if module in module_definition_cache:
        result0 = module_definition_cache[module]
        result = deepcopy(result0)
        if "__init__" in result and "code" not in result:
            result = {
                "code": result,
                "language": "python",
                "type": "interpreted"
            }
        _restore_dependencies(result)
    else:
        def getsource(module):
            with open(module.__file__) as f:
                #code = inspect.getsource(module).strip("\n")
                code = f.read().strip("\n")
            return code
        module_file = module.__file__
        if module_file.endswith("__init__.py"):
            module_dir = pathlib.PosixPath(module_file).parent
            dirdict = {}
            for modname, mod in sys.modules.items():
                if not modname.startswith(module.__name__):
                    continue
                modfile0 = pathlib.PosixPath(mod.__file__)
                modfile1 = modfile0.relative_to(module_dir)
                modfile = modfile1.as_posix()
                dirdict[modfile] = getsource(mod)
            result = pypackage_to_moduledict(dirdict)
        else:
            code = getsource(module)
            result = {
                "code": code,
                "language": "python",
                "type": "interpreted"
            }
    return result
