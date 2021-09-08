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
if __name__ == "__main__":
    import sys
    pycode = open(sys.argv[1]).read()
    if len(sys.argv) == 3:
        package_name = sys.argv[2]
    else:
        package_name = None
    deps = pypackage_dependencies(pycode, package_name, False)
    print(deps)
