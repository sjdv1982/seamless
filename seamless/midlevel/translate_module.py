from copy import deepcopy
from ..core import cell as core_cell, transformer, context
from ..metalevel.stdgraph import load as load_stdgraph
from .util import get_path


import inspect

def gen_moduledict_generic(module_code, module_type, language, dependencies):
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
    checksum = node.get("checksum")
    if checksum is not None:
        codecell._set_checksum(checksum, initial=True)
    if "mount" in node:
        mount = deepcopy(node["mount"])
        if node.get("multi"):
            mount["as_directory"] = True
            codecell.mount(**mount)
        else:
            codecell2 = core_cell("mixed")
            subcontext.code2 = codecell2
            codecell3 = core_cell("text")
            subcontext.code3 = codecell3
            codecell3.mount(**mount)
            mode = mount.get("mode", "rw")
            if mode == "rw" :
                codecell2.bilink(codecell)
                codecell3.bilink(codecell2)
            elif mode == "r":
                codecell2.connect(codecell)
                codecell3.connect(codecell2)
            elif mode == "w":
                codecell.connect(codecell2)
                codecell2.connect(codecell3)

    subcontext.module_cell = core_cell("plain")
    if node.get("multi"):
        sctx = load_stdgraph("multi_module")
        subcontext.get_pypackage_dependencies_code = core_cell("python")
        subcontext.get_pypackage_dependencies_code.set(sctx.get_pypackage_dependencies_code.value)
        subcontext.pypackage_to_moduledict_code = core_cell("python")
        subcontext.pypackage_to_moduledict_code.set(sctx.pypackage_to_moduledict_code.value)
        c = subcontext.gen_moduledict = transformer({
            "internal_package_name": ("input", "str"),
            "pypackage_dirdict": ("input", "plain"),
            "get_pypackage_dependencies": ("input", "plain", "module"),
            "result": ("output", "plain")
        })
        subcontext.pypackage_to_moduledict_code.connect(c.code)
        internal_package_name = node.get("internal_package_name", "")
        c.internal_package_name.cell().set(internal_package_name)
        codecell.connect(c.pypackage_dirdict)

        subcontext.gen_moduledict_helper = transformer({
            "module_type": ("input", "str"),
            "language": ("input", "str"),
            "module_code": ("input", "plain"),
            "dependencies": ("input", "plain"),
            "result": ("output", "plain")
        })
        subcontext.gen_moduledict_helper.code.cell().set(
            inspect.getsource(gen_moduledict_generic)
        )
        subcontext.gen_moduledict_helper.module_type.cell().set("interpreted")
        subcontext.gen_moduledict_helper.language.cell().set("python")
        subcontext.gen_moduledict_helper.dependencies.cell().set([])

        subcontext.get_pypackage_dependencies_code.connect(
            subcontext.gen_moduledict_helper.module_code
        )
        subcontext.get_pypackage_dependencies_moduledict = core_cell("plain")
        subcontext.gen_moduledict_helper.result.connect(
            subcontext.get_pypackage_dependencies_moduledict
        )
        subcontext.get_pypackage_dependencies_moduledict.connect(
            c.get_pypackage_dependencies
        )
    else:
        # non-multi
        subcontext.gen_moduledict = transformer({
            "module_type": ("input", "str"),
            "language": ("input", "str"),
            "module_code": ("input", "plain"),
            "dependencies": ("input", "plain"),
            "result": ("output", "plain")
        })
        subcontext.gen_moduledict.code.cell().set(
            inspect.getsource(gen_moduledict_generic)
        )
        subcontext.gen_moduledict.module_type.cell().set(module_type)
        subcontext.gen_moduledict.language.cell().set(language)
        subcontext.gen_moduledict.dependencies.cell().set(dependencies)
        codecell.connect(subcontext.gen_moduledict.module_code)

    subcontext.gen_moduledict.result.connect(subcontext.module_cell)

    namespace[path, "source"] = subcontext.module_cell, node
    namespace[path, "target"] = codecell, node

    return subcontext
