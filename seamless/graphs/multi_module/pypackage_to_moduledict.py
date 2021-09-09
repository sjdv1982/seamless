code = {}
if internal_package_name is not None and len(internal_package_name):
    code["__name__"] = internal_package_name
from .get_pypackage_dependencies import get_pypackage_dependencies
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
analyze(pypackage_dirdict, "")
result = {
    "language": "python",
    "type": "interpreted",
    "code": code,
}