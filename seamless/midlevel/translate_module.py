from seamless.core import cell as core_cell, transformer, context
from .util import get_path

import inspect

def gen_module_cell(module_code, module_type, language):
    return {
        "type": module_type,
        "language": language,
        "code": module_code,
    }

def translate_module(node, root, namespace, inchannels, outchannels):
    module_type = node["module_type"]
    language = node["language"]

    path = node["path"]
    parent = get_path(root, path[:-1], None, None)
    name = path[-1]
    for c in inchannels + outchannels:
        assert not len(c) #should have been checked by highlevel
    subcontext = context(toplevel=False)
    setattr(parent, name, subcontext)

    codecell = core_cell("text")
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
        codecell.mount(**node["mount"])

    subcontext.module_cell = core_cell("plain")
    subcontext.gen_module_cell = transformer({
        "module_type": ("input", "str"),
        "language": ("input", "str"),
        "module_code": ("input", "text"),
        "result": ("output", "plain")
    })
    subcontext.gen_module_cell.code.cell().set(
        inspect.getsource(gen_module_cell)
    )
    subcontext.gen_module_cell.module_type.cell().set(module_type)
    subcontext.gen_module_cell.language.cell().set(language)
    codecell.connect(subcontext.gen_module_cell.module_code)

    subcontext.gen_module_cell.result.connect(subcontext.module_cell)

    namespace[path, "source"] = subcontext.module_cell, node
    namespace[path, "target"] = codecell, node

    return subcontext