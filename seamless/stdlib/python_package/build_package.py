result = {}
if package_name is not None:
    result["__name__"] = package_name
from .analyze_dependencies import analyze_dependencies
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
        deps0 = analyze_dependencies(pycode, package_name)
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
            deps.append(dep2)
        deps = sorted(list(deps))
        item = {
            "language": "python",
            "code": pycode,
            "dependencies": deps,
        }
        result[f] = item
analyze(package_dirdict, "")