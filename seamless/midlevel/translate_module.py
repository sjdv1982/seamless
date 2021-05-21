from seamless.core import cell as core_cell, transformer, context
from .util import get_path

import inspect

def gen_module_cell(module_code, module_type, language, dependencies):
    result = {
        "type": module_type,
        "language": language,
        "code": module_code,
    }
    if len(dependencies):
        result["dependencies"] = dependencies
    return result

def translate_module(node, root, namespace, inchannels, outchannels):
    module_type = node["module_type"]
    language = node["language"]
    dependencies = node["dependencies"]

    path = node["path"]
    parent = get_path(root, path[:-1], None, None)
    name = path[-1]
    for c in inchannels + outchannels:
        assert not len(c) #should have been checked by highlevel
    subcontext = context(toplevel=False)
    setattr(parent, name, subcontext)

    codecell = core_cell("plain")
    subcontext.code = codecell
    if node.get("fingertip_no_recompute"):
        codecell._fingertip_recompute = False
    if node.get("fingertip_no_remote"):
        codecell._fingertip_remote = False
    pathstr = "." + ".".join(path)
    checksum = node.get("checksum")
    if checksum is not None:
        codecell._set_checksum(checksum, initial=True)
    if "mount" in node:
        codecell2 = core_cell("text")
        subcontext.code2 = codecell2
        codecell2.mount(**node["mount"])
        mode = node["mount"].get("mode", "rw")
        if mode == "rw" :
            codecell2.bilink(codecell)
        elif mode == "r":
            codecell2.connect(codecell)
        elif mode == "w":
            codecell.connect(codecell2)

    subcontext.module_cell = core_cell("plain")
    subcontext.gen_module_cell = transformer({
        "module_type": ("input", "str"),
        "language": ("input", "str"),
        "module_code": ("input", "plain"),
        "dependencies": ("input", "plain"),
        "result": ("output", "plain")
    })
    subcontext.gen_module_cell.code.cell().set(
        inspect.getsource(gen_module_cell)
    )
    subcontext.gen_module_cell.module_type.cell().set(module_type)
    subcontext.gen_module_cell.language.cell().set(language)
    subcontext.gen_module_cell.dependencies.cell().set(dependencies)
    codecell.connect(subcontext.gen_module_cell.module_code)

    subcontext.gen_module_cell.result.connect(subcontext.module_cell)

    namespace[path, "source"] = subcontext.module_cell, node
    namespace[path, "target"] = codecell, node

    return subcontext
