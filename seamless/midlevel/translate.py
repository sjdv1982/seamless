"""
Translation macro

Translates mid-level into low-level
The mid-level is assumed to be correct; any errors should be caught there
"""

from warnings import warn
from collections import OrderedDict
from functools import partial

from seamless.core import (cell as core_cell,
 transformer, reactor, context, macro, StructuredCell)

from . import copying
from .util import as_tuple, get_path, get_path_link, find_channels, build_structured_cell

import logging
logger = logging.getLogger("seamless")

def print_info(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)

def print_warning(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)

def print_debug(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)

def print_error(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)

direct_celltypes = (
    "text", "plain", "mixed", "binary",
    "cson", "yaml", "str", "bytes", "int", "float", "bool",
    "checksum"
)

empty_dict_checksum = 'd0a1b2af1705c1b8495b00145082ef7470384e62ac1c4d9b9cdbbe0476c28f8c'

def set_structured_cell_from_checksum(cell, checksum):
    trigger = False
    """
    if "temp" in checksum:
        assert len(checksum) == 1, checksum.keys()
        temp_checksum = checksum["temp"]
        if cell.hash_pattern is not None:
            temp_cs = bytes.fromhex(temp_checksum)
            temp_cs2 = apply_hash_pattern_sync(
                temp_cs, cell.hash_pattern
            )
            temp_checksum = temp_cs2.hex()
        cell.auth._set_checksum(temp_checksum, initial=True, from_structured_cell=False)
        trigger = True
    else:
    """
    if "value" in checksum:
        # not done! value calculated anew...
        """
        cell._data._set_checksum(
            checksum["value"],
            from_structured_cell=True,
            initial=True
        )
        trigger = True
        """

    if "buffer" in checksum:
        # not done! value calculated anew...
        """
        cell.buffer._set_checksum(
            checksum["buffer"],
            from_structured_cell=True,
            initial=True
        )
        trigger = True
        """

    if "auth" in checksum:
        if cell.auth is None:
            msg = "Warning: %s has no authority, but an auth checksum is present"
            print(msg % cell)
        else:
            cell.auth._set_checksum(
                checksum["auth"],
                from_structured_cell=True,
                initial=True
            )
            cell._data._void = False
            cell._data._status_reason = None
            trigger = True

    schema_checksum = empty_dict_checksum
    if "schema" in checksum:
        schema_checksum = checksum["schema"]        
    cell.schema._set_checksum(
        schema_checksum,
        from_structured_cell=True,
        initial=True
    )
    trigger = True

    if trigger:
        cell._get_manager().structured_cell_trigger(cell)

def translate_cell(node, root, namespace, inchannels, outchannels):
    path = node["path"]
    parent = get_path(root, path[:-1], None, None)
    name = path[-1]
    ct = node["celltype"]
    if ct == "structured":
        datatype = node["datatype"]
        ### TODO: harmonize datatype with schema type
        hash_pattern = node["hash_pattern"]
        mount = node.get("mount")
        child = build_structured_cell(
          parent, name,
          inchannels, outchannels,
          fingertip_no_remote=node.get("fingertip_no_remote", False),
          fingertip_no_recompute=node.get("fingertip_no_recompute", False),
          hash_pattern=hash_pattern,
          mount=mount
        )
        for inchannel in inchannels:
            cname = child.inchannels[inchannel].subpath
            if cname == "self":
                cpath = path
            else:
                if isinstance(cname, str):
                    cname = (cname,)
                cpath = path + cname
            namespace[cpath, "target"] = child.inchannels[inchannel], node
        for outchannel in outchannels:
            cpath = path + outchannel
            namespace[cpath, "source"] = child.outchannels[outchannel], node
    else: #not structured
        for c in inchannels + outchannels:
            assert not len(c) #should have been checked by highlevel
        if ct == "code":
            if node["language"] in ("python", "ipython"):
                if node.get("transformer"):
                    child = core_cell("transformer")
                else:
                    child = core_cell(node["language"])
            else:
                child = core_cell("text")
                child.set_file_extension(node["file_extension"])

        elif ct in direct_celltypes:
            child = core_cell(ct)
            if ct == "mixed":
                child._hash_pattern = node.get("hash_pattern")
        else:
            raise ValueError(ct) #unknown celltype; should have been caught by high level
        if node.get("fingertip_no_recompute"):
            child._fingertip_recompute = False
        if node.get("fingertip_no_remote"):
            child._fingertip_remote = False
    setattr(parent, name, child)
    pathstr = "." + ".".join(path)
    checksum = node.get("checksum")
    if checksum is not None:
        if ct == "structured":
            set_structured_cell_from_checksum(child, checksum)
        else:
            if "value" in checksum and not len(inchannels):
                child._set_checksum(checksum["value"], initial=True)
            """
            if "temp" in checksum:
                assert len(checksum) == 1, checksum.keys()
                child._set_checksum(checksum["temp"], initial=True)
            """
    if ct != "structured":
        if "file_extension" in node:
            child.set_file_extension(node["file_extension"])
        if "mount" in node:
            child.mount(**node["mount"])

    return child

def translate_connection(node, namespace, ctx):
    from ..core.cell import Cell
    from ..core.structured_cell import Inchannel, Outchannel
    from ..core.worker import Worker, PinBase
    source_path, target_path = node["source"], node["target"]

    source, source_node, source_is_edit = get_path(
      ctx, source_path, namespace, False,
      return_node = True
    )
    if isinstance(source, StructuredCell):
        source = source.outchannels[()]
    target, target_node, target_is_edit = get_path(
      ctx, target_path, namespace, True,
      return_node=True
    )
    if isinstance(target, StructuredCell):
        target = target.inchannels[()]

    def do_connect(source, target):
        if source_is_edit or target_is_edit:
            msg = "Cannot set up an edit link involving a structured cell: %s (with %s)"
            if not isinstance(source, Cell):
                raise Exception(msg % (source.structured_cell(), target))
            if not isinstance(target, Cell):
                raise Exception(msg % (target.structured_cell(), source))
            source.bilink(target)
            return

        if isinstance(source, Cell) or isinstance(target, Cell):
            source.connect(target)
            return

        n = 0
        while 1:
            n += 1
            con_name = "CONNECTION_" + str(n)
            if con_name not in ctx._children:
                break
        hash_pattern = source.hash_pattern
        if isinstance(source, Outchannel):
            if hash_pattern is not None:
                hash_pattern = access_hash_pattern(hash_pattern, source.subpath)
        intermediate = core_cell("mixed", hash_pattern=hash_pattern)
        setattr(ctx, con_name, intermediate)
        source.connect(intermediate)
        intermediate.connect(target)


    if not isinstance(source, (Worker, PinBase, Outchannel, Cell)):
        raise TypeError(source)
    if not isinstance(target, (Worker, PinBase, Inchannel, Cell)):
        raise TypeError(target)
    do_connect(source, target)

def translate_link(node, namespace, ctx):
    first = get_path_link(
      ctx, node["first"], namespace
    )
    second = get_path_link(
      ctx, node["second"], namespace
    )
    first.bilink(second)

translate_compiled_transformer = None
translate_bash_transformer = None
translate_docker_transformer = None

def import_before_translate(graph):
    global translate_compiled_transformer
    global translate_bash_transformer
    global translate_docker_transformer
    impvars = (
        "translate_compiled_transformer",
        "translate_bash_transformer",
        "translate_docker_transformer"
    )
    if all([globals()[var] is not None for var in impvars]):
        return
    nodes = graph["nodes"]
    for node in nodes:
        t = node["type"]
        if t == "transformer":
            if node["compiled"]:
                from .translate_compiled_transformer import translate_compiled_transformer
            elif node["language"] == "bash":
                from .translate_bash_transformer import translate_bash_transformer
            elif node["language"] == "docker":
                from .translate_docker_transformer import translate_docker_transformer

def translate(graph, ctx, environment):
    from ..core.macro_mode import curr_macro
    if curr_macro() is None:
        print_info("*" * 30 + "TRANSLATE" + "*" * 30)
    #import traceback; stack = traceback.extract_stack(); print("TRANSLATE:"); print("".join(traceback.format_list(stack[:3])))
    nodes, connections = graph["nodes"], graph["connections"]
    contexts = {con["path"]: con for con in nodes if con["type"] == "context"}
    for path in sorted(contexts.keys(), key=lambda k:len(k)):
        parent = get_path(ctx, path[:-1], None, is_target=False)
        name = path[-1]
        c = context()
        setattr(parent, name, c)
        # No need to add it to namespace, as long as the low-level graph structure is imitated

    connection_paths = [(con["source"], con["target"]) for con in connections if con["type"] == "connection"]

    namespace = {}
    for node in nodes:
        t = node["type"]
        if t in ("context", "link"):
            continue
        path = node["path"]

    for node in nodes:
        t = node["type"]
        if t in ("context", "link"):
            continue
        path = node["path"]
        if t == "transformer":
            inchannels, outchannels = find_channels(node["path"], connection_paths)
            language = node["language"]
            if node["compiled"]:
                from .translate_compiled_transformer import translate_compiled_transformer
                translate_compiled_transformer(node, ctx, namespace, inchannels, outchannels)
            elif language == "bash":
                translate_bash_transformer(node, ctx, namespace, inchannels, outchannels)
            elif language == "docker":
                translate_docker_transformer(node, ctx, namespace, inchannels, outchannels)
            else:
                ipy_template = None
                py_bridge = None
                if language not in ("python", "ipython"):                    
                    ok = False                    
                    if environment is not None:
                        try:
                            ipy_template = environment.get_ipy_template(language)
                            ok = True
                        except KeyError:
                            pass
                        try:
                            py_bridge = environment.get_py_bridge(language)
                            ok = True
                        except KeyError:
                            pass
                        if ipy_template is not None and py_bridge is not None:
                            msg = "Language '{}' has an IPython template AND a Python bridge"
                            raise ValueError(msg.format(language))
                    if not ok:
                        raise NotImplementedError(language)
                translate_py_transformer(
                    node, ctx, namespace, inchannels, outchannels,
                    ipy_template=ipy_template,
                    py_bridge=py_bridge
                )                
        elif t == "macro":
            if node["language"]  != "python":
                raise NotImplementedError(node["language"])
            inchannels, outchannels = find_channels(node["path"], connection_paths)
            translate_macro(node, ctx, namespace, inchannels, outchannels)
        elif t == "cell":
            inchannels, outchannels = find_channels(path, connection_paths)
            translate_cell(node, ctx, namespace, inchannels, outchannels)
        elif t == "module":
            inchannels, outchannels = find_channels(path, connection_paths)
            translate_module(node, ctx, namespace, inchannels, outchannels)
        elif t == "libinstance":
            msg = "Libinstance '%s' was not removed during pre-translation"
            raise TypeError(msg % str(path))
        else:
            raise TypeError(t)
        node.pop("UNTRANSLATED", None)
        node.pop("UNSHARE", None)

    namespace2 = OrderedDict()
    for k in sorted(namespace.keys(), key=lambda k:-len(k)):
        namespace2[k] = namespace[k]

    for connection in connections:
        if connection["type"] == "connection":
            translate_connection(connection, namespace2, ctx)
        elif connection["type"] == "link":
            translate_link(connection, namespace2, ctx)
        elif connection["type"] == "virtual":
            pass
        else:
            raise TypeError(connection["type"])

from .translate_py_transformer import translate_py_transformer
from .translate_macro import translate_macro
from .translate_module import translate_module
'''
# imported only at need...
from .translate_bash_transformer import translate_bash_transformer
from .translate_docker_transformer import translate_docker_transformer
from .translate_compiled_transformer import translate_compiled_transformer
'''
from ..core.protocol.deep_structure import apply_hash_pattern_sync, access_hash_pattern