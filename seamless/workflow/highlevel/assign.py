import inspect
from copy import deepcopy


def check_libinstance_subcontext_binding(ctx, path):
    for node in ctx._graph.nodes.values():
        if node["type"] == "libinstance":
            libpath = node["libpath"]
            lib = ctx._get_lib(tuple(libpath))
            params = lib["params"]
            for argname, par in params.items():
                if par["type"] == "context":
                    argvalue = node["arguments"].get(argname)
                    if argvalue is not None:
                        if path[: len(argvalue)] == argvalue:
                            ctx._translate()
                            return


from . import getConstantTypes
from .Cell import Cell, FolderCell, get_new_cell, get_new_foldercell
from .DeepCell import DeepCellBase, DeepCell, DeepFolderCell
from .Module import Module, get_new_module


from .Resource import Resource
from .Transformer import Transformer
from .Macro import Macro
from .proxy import Proxy, CodeProxy, HeaderProxy
from . import parse_function_code
from .Link import Link
from .compiled import CompiledObjectDict, CompiledObjectWrapper
from .SchemaWrapper import SchemaWrapper


def _remove_independent_mountshares(hcell):
    if "mount" in hcell:
        if "r" in hcell["mount"]["mode"]:
            hcell.pop("mount")
    if "share" in hcell:
        if hcell["share"]["readonly"]:
            hcell.pop("mount", None)


def under_libinstance_control(nodedict, path):
    lp = len(path)
    if lp == 0:
        return False
    elif path in nodedict:
        longest_path = path
    elif lp == 1:
        return False
    else:
        longest_path = None
        llp = 0  # length of longest path
        for nodepath in nodedict:
            lnp = len(nodepath)
            if lnp >= lp:
                continue
            if lnp <= llp:
                continue
            if path[:lnp] == nodepath:
                longest_path = nodepath
                llp = lnp
                if llp == lp - 1:
                    break
        if longest_path is None:
            return False
    node = nodedict[longest_path]
    if node["type"] == "libinstance":
        return node
    return None


def assign_constant(ctx, path, value, help_context=False):
    old = None
    if path in ctx._children:
        old = ctx._children[path]
        if isinstance(old, Cell):
            removed = ctx.remove_connections(path, endpoint="target")
            if removed:
                ctx._translate()
                hcell = old._get_hcell()
                hcell["UNTRANSLATED"] = True
            hcell = old._get_hcell()
            if not hcell.get("UNTRANSLATED"):
                cell = old._get_cell()
                if cell.has_independence():
                    old._set(value)
                    return False
                else:
                    return True
            else:
                old._set(value)
                return False
        elif isinstance(old, Module):
            removed = ctx.remove_connections(path, endpoint="target")
            if removed:
                ctx._translate()
                hnode = old._get_hnode()
                hnode["UNTRANSLATED"] = True
            old.set(value)
            return False
        else:
            raise AttributeError(path)  # already exists, but not a Cell or Module
    if old is None:
        Cell(parent=ctx, path=path)  # inserts itself as child
        cell = get_new_cell(path)
        if help_context:
            cell["celltype"] = "text"
        else:
            cell["celltype"] = "structured"
    else:
        cell = old._get_hcell()
    if callable(value):
        code, _, _ = parse_function_code(value)
        if old is None:
            cell["celltype"] = "python"
            value = code
        elif old["celltype"] in ("python", "ipython"):
            value = code

    cell["TEMP"] = value
    ### json.dumps(cell)
    ctx._graph[0][path] = cell
    ctx._translate()


def assign_resource(ctx, path, value):
    assign_constant(ctx, path, value.data)
    child = ctx._children[path]
    child.mount(value.filename)


def assign_transformer(ctx, path, func):
    existing_transformer = None
    if path in ctx._children:
        old = ctx._children[path]
        if isinstance(old, Cell):
            old.set(func)
        elif isinstance(old, Transformer):
            existing_transformer = old
        else:
            ctx._destroy_path(path)

    assert callable(func)
    code, _, _ = parse_function_code(func)
    parameters = []
    for pname, p in inspect.signature(func).parameters.items():
        # TODO: look at default parameters, make them optional
        if pname.startswith("SPECIAL__"):
            raise TypeError(
                "Pin name '{}' must not be like a special pin name".format(pname)
            )
        if p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL):
            parameters.append(pname)
    if existing_transformer is not None:
        old_pins = list(existing_transformer.pins)
        for old_pin in old_pins:
            if old_pin not in parameters:
                existing_transformer.pins[old_pin] = None
                ctx._translate()
        for pname in parameters:
            if pname not in old_pins:
                existing_transformer.pins[pname] = {}
                ctx._translate()
        existing_transformer.code = code
    else:
        tf = Transformer(code=code, pins=parameters)
        tf._init(parent=ctx, path=path, set_node=True)
        # inserts itself as child
        assert ctx._children[path] is tf
        ctx._translate()


def assign_transformer_copy(ctx, path, tf):
    parent = tf._parent()
    assert parent is ctx or parent is None
    if path in ctx._children:
        ctx._destroy_path(path)

    tf_node = deepcopy(tf._get_htf())
    tf_node["path"] = path
    nodes, connections = ctx._graph[:2]
    nodes[path] = tf_node

    tf_path = tf._path
    if tf_path is not None:
        lp = len(tf_path)
        for con in list(connections):
            if con["type"] != "connection":
                continue
            c = con["target"]
            if c[:lp] == tf_path:
                con2 = deepcopy(con)
                con2["target"] = path + c[lp:]
                connections.append(con2)
    tf = Transformer()
    tf._init(parent=ctx, path=path, set_node=False)
    # inserts itself as child
    assert ctx._children[path] is tf
    ctx._translate()


def assign_libinstance(ctx, path, libinstance):
    libinstance._bind(ctx, path)


def assign_connection(ctx, source, target, standalone_target, exempt=None):
    # "standalone_target" is False for subcells or proxywrappers, True otherwise
    if exempt is None:
        exempt = []
    nodedict = ctx._graph[0]
    libinstance_source_node = under_libinstance_control(nodedict, source)
    if libinstance_source_node is not None:
        try:
            lib = ctx._get_lib(tuple(libinstance_source_node["libpath"]))
            p = libinstance_source_node["path"]
            if len(source) != len(p) + 1:
                raise ValueError
            params = lib["params"]
            attr = source[-1]
            if attr not in params:
                raise AttributeError
            par = params[attr]
            if par["io"] != "output":
                raise AttributeError
            arguments = libinstance_source_node["arguments"]
            from .library.argument import parse_argument

            t = ctx._children[target]
            arguments[attr] = parse_argument(attr, t, par)
            return True
        except Exception:
            msg = "Cannot connect from path under libinstance control: {}"
            raise Exception(msg.format(source)) from None
    if under_libinstance_control(nodedict, target):
        msg = "Cannot connect to path under libinstance control: {}"
        raise Exception(msg.format(target))
    if standalone_target:
        if target not in ctx._children:
            assign_constant(ctx, target, None)
        t = ctx._children[target]
        assert isinstance(t, (Cell, Module, DeepCellBase))
        if isinstance(t, (Cell, DeepCellBase)):
            hcell = t._get_hcell()
            if "TEMP" in hcell:
                hcell.pop("TEMP")
            elif "checksum" in hcell:
                hcell["checksum"].pop("value", None)
                if isinstance(t, (DeepCell, DeepFolderCell)):
                    hcell["checksum"].pop("origin", None)
                    if isinstance(ctx._children.get(source), DeepCellBase):
                        hcell["checksum"].pop("keyorder", None)
                else:
                    hcell["checksum"].pop("auth", None)
        else:
            hnode = t._get_hnode()
            if "TEMP" in hnode:
                hnode.pop("TEMP")
            else:
                hnode.pop("checksum", None)
    lt = len(target)

    def keep_con(con):
        if con["type"] == "link":
            first = con["first"]
            if first[:lt] == target:
                return False
            second = con["second"]
            if second[:lt] == target:
                return False
            return True
        ctarget = con["target"]
        if ctarget[:lt] != target:
            return True
        if target[: len(ctarget)] != ctarget:
            return True
        for e in exempt:
            if ctarget[: len(e)] == e:
                return True
        return False

    ctx._graph[1][:] = filter(keep_con, ctx._graph[1])
    if standalone_target:
        t = ctx._children[target]
        assert isinstance(t, (Module, DeepCellBase)) or not t.get_links()
    assert source in ctx._children or source[:-1] in ctx._children, source
    s = None
    if source in ctx._children:
        s = ctx._children[source]
        if isinstance(s, Cell):
            hcell = s._get_hcell()
            if hcell.get("constant"):
                raise TypeError("Cannot assign to constant cell")
        elif isinstance(s, (Module, DeepCellBase)):
            if isinstance(s, DeepCellBase):
                if not standalone_target:
                    t2 = ctx._children.get(target[:-1])
                    if not isinstance(t2, Transformer):
                        raise ValueError("Cannot assign deep cell to subcell")
                elif isinstance(t, (Cell, DeepCellBase)):
                    if t.hash_pattern is None and t.celltype != "checksum":
                        if isinstance(s, DeepFolderCell):
                            msg = """ERROR: assigning a DeepFolderCell to a Cell

When accessed, Cells have their complete content loaded into memory.
This is not the case for DeepFolderCells, whose content can be very large in size.

Therefore, the direct assignment of a DeepFolderCell to a Cell is not allowed.

You can instead assign a DeepFolderCell to a FolderCell.
FolderCells have the same internal memory-efficient representation as DeepFolderCells,
but they are assumed to be small enough to be mounted to disk.

If you really want to do so, assigning a FolderCell to a Cell is allowed.
"""

                        else:
                            msg = """ERROR: assigning a DeepCell to a Cell

When accessed, Cells have their complete content loaded into memory.
This is not the case for DeepCells, whose content can be very large in size.

Therefore, the direct assignment of a DeepCell to a Cell is by default not allowed.

If you really want to do this, create an intermediate SimpleDeepCell,
assign the DeepCell to the SimpleDeepCell, and the SimpleDeepCell to the Cell.
"""
                        raise Exception(msg)
                elif isinstance(t, Base):
                    raise ValueError("Cannot assign deep cell to {}".format(type(t)))
            pass
        else:
            raise TypeError(type(s))
    else:
        source_parent_path = source[:-1]
        if source_parent_path not in ctx._children:
            raise KeyError("Unknown path '{}'".format(source_parent_path))
        source_parent = ctx._children[source_parent_path]
        assert isinstance(source_parent, (Transformer, Macro)), source_parent
        attr = source[-1]
        ok = False
        if attr == "SCHEMA":
            ok = True
        elif attr == "RESULTSCHEMA" and isinstance(source_parent, Transformer):
            ok = True
        if not ok:
            s = getattr(source_parent, attr)
            assert isinstance(s, Proxy), s
            if isinstance(s, (CodeProxy, HeaderProxy)):
                pass
            elif (
                isinstance(source_parent, Transformer) and attr == source_parent.RESULT
            ):
                source = source_parent_path
                s = None
            elif attr in source_parent.pins:
                pin = source_parent.pins[attr]
                if isinstance(source_parent, Macro):
                    assert pin["io"] == "output", (source, pin["io"])
            else:
                raise TypeError("No output pin '{}'".format(attr))
    if s is not None and s._virtual_path is not None:
        source = s._virtual_path
    if standalone_target:
        t = ctx._children[target]
        assert isinstance(t, (Cell, Module, DeepCellBase))
        if t._virtual_path is not None:
            target = t._virtual_path
    connection = {"type": "connection", "source": source, "target": target}
    ctx._graph[1].append(connection)


def _assign_context2(ctx, new_nodes, new_connections, path, runtime, *, fast):
    from .Context import Context

    assert isinstance(ctx, Context)
    if fast:
        assert runtime
    if runtime:
        nodes, connections, _, _ = ctx._runtime_graph
    else:
        nodes, connections, _, _ = ctx._graph
    if not fast:
        for p in list(nodes.keys()):
            if p[: len(path)] == path or p[: len(path) + 1] == ("HELP",) + path:
                nodes.pop(p)
        for con in list(connections):
            if con["type"] == "connection":
                source, target = con["source"], con["target"]
                if (
                    source[: len(path)] != path
                    and source[: len(path) + 1] != ("HELP",) + path
                ):
                    continue
                if (
                    target[: len(path)] != path
                    and target[: len(path) + 1] != ("HELP",) + path
                ):
                    continue
                connections.remove(con)
    nodes[path] = {"path": path, "type": "context"}
    new_nodes = deepcopy(new_nodes)
    new_connections = deepcopy(new_connections)
    targets = set()
    for con in new_connections:
        targets.add(tuple(con["target"]))
    indexed_nodepaths = []
    for node in new_nodes:
        old_path = tuple(node["path"])
        if old_path[0] == "HELP":
            pp = ("HELP",) + path + old_path[1:]
        else:
            pp = path + old_path
        node["path"] = pp
        nodetype = node["type"]
        indexed_nodepaths.append(pp)
        nodes[pp] = node
        if not runtime and nodetype not in ("context", "libinstance"):
            node["UNTRANSLATED"] = True
        remove_checksum = []
        if nodetype == "cell":
            if not fast:
                Cell(parent=ctx, path=pp)
            remove_checksum.append("temp")
            if node["celltype"] == "structured":
                remove_checksum.append("value")
                remove_checksum.append("buffered")
            else:  # simple cell, can be targeted at most once
                if old_path in targets:
                    remove_checksum.append("value")
        elif nodetype == "transformer":
            if not fast:
                Transformer()._init(parent=ctx, path=pp, set_node=False)
            remove_checksum += ["input_temp", "input", "input_buffer", "result"]
            potential = ("code", "schema", "result_schema", "main_module")
            for pot in potential:
                if old_path + (pot,) in targets:
                    remove_checksum.append(pot)
            if runtime:
                node.pop("UNTRANSLATED", None)
        elif nodetype == "macro":
            if not fast:
                Macro(parent=ctx, path=pp)
            remove_checksum += ["param_temp", "param", "param_buffer"]
            potential = ("code", "schema")
            for pot in potential:
                if old_path + (pot,) in targets:
                    remove_checksum.append(pot)
            if runtime:
                node.pop("UNTRANSLATED", None)
        elif nodetype == "module":
            if not fast:
                Module(parent=ctx, path=pp)
            if old_path in targets:
                node.pop("checksum", None)
        elif nodetype == "context":
            pass
        elif nodetype == "libinstance":
            nodelib = ctx._graph.lib[tuple(node["libpath"])]
            for argname, arg in list(node["arguments"].items()):
                param = nodelib["params"][argname]
                if param["type"] in ("cell", "context"):
                    if isinstance(arg, tuple):
                        arg = list(arg)
                    if not isinstance(arg, list):
                        arg = [arg]
                    arg = list(path) + arg
                elif param["type"] == "celldict":
                    for k, v in arg.items():
                        if isinstance(v, tuple):
                            v = list(v)
                        if not isinstance(v, list):
                            v = [v]
                        v = list(path) + v
                node["arguments"][argname] = arg
        else:
            raise TypeError(nodetype)
        if "checksum" in node:
            cs = node["checksum"]
            for item in remove_checksum:
                cs.pop(item, None)
    indexed_connections = []
    for con in new_connections:
        for attr in "source", "target":
            old_path = tuple(con[attr])
            if old_path[0] == "HELP":
                pp = ("HELP",) + path + old_path[1:]
            else:
                pp = path + old_path
            con[attr] = pp
        indexed_connections.append(con)
        connections.append(con)
    if fast:
        ctx._add_runtime_index(path, indexed_nodepaths, indexed_connections)


def _assign_context(ctx, new_nodes, new_connections, path, runtime, *, fast=False):
    if runtime and not fast:
        old_graph = deepcopy(ctx._graph)
    ctx._destroy_path(path, runtime=runtime, fast=fast)
    ctx._destroy_path(("HELP",) + path, runtime=runtime, fast=fast)
    _assign_context2(ctx, new_nodes, new_connections, path, runtime, fast=fast)
    if not fast:
        graph = ctx._runtime_graph if runtime else ctx._graph
        subctx = graph.nodes[path]
        assert subctx["type"] == "context", path
    if runtime:
        if not fast:
            graph2 = deepcopy(ctx._graph)
            assert (
                old_graph == graph2  # pylint: disable=possibly-used-before-assignment
            )
    else:
        ctx._translate()


def assign_context(ctx, path, value):
    from .Context import Context
    from .SubContext import SubContext

    if isinstance(value, Context):
        graph = value._get_graph(runtime=False, do_unchecksum=False)
    elif isinstance(value, SubContext):
        graph = value.get_graph(runtime=False)
    else:
        raise TypeError(value)
    for lib in graph["lib"]:
        lpath = tuple(lib["path"])
        lib["path"] = lpath
        ctx._set_lib(lpath, lib)
    new_nodes, new_connections = graph["nodes"], graph["connections"]
    _assign_context(ctx, new_nodes, new_connections, path, runtime=False)


def assign_to_deep_subcell(cell, attr, value):
    ConstantTypes = getConstantTypes()

    hcell = cell._get_hcell()
    ctx = cell._parent()
    if isinstance(value, Cell):
        raise AttributeError(
            "Can only assign cells to DeepCell.blacklist and DeepCell.whitelist"
        )
    elif isinstance(value, ConstantTypes):
        check_libinstance_subcontext_binding(ctx, (attr,))
        removed1 = ctx.remove_connections(
            cell._path + (attr,), endpoint="link", match="all"
        )
        removed2 = ctx.remove_connections(
            cell._path + (attr,), endpoint="target", match="all"
        )
        removed = removed1 or removed2
        hcell = cell._get_hcell()
        untranslated = hcell.get("UNTRANSLATED")
        if removed:
            ctx._translate()
        if untranslated:
            if isinstance(cell, (DeepCell, DeepFolderCell)):
                if not isinstance(attr, str):
                    raise TypeError(type(attr))
                temp_value = hcell.get("TEMP", {})
            else:
                """
                assert isinstance(cell, DeepListCell)
                if not isinstance(attr, int):
                    raise TypeError(type(attr))
                temp_value = hcell.get("TEMP", [])
                if isinstance(temp_value, list) and len(temp_value) <= attr:
                    for d in range(len(temp_value), attr+1):
                        temp_value.append(None)
                """
                raise NotImplementedError
            temp_value[attr] = value
            hcell["TEMP"] = temp_value
            return
        handle = cell._handle
        if isinstance(attr, int):
            handle[attr] = value
        else:
            setattr(handle, attr, value)
    else:
        raise TypeError(value)


def assign_to_subcell(cell, path, value):
    from ..core.structured_cell import StructuredCell

    ConstantTypes = getConstantTypes()

    hcell = cell._get_hcell()
    if hcell.get("constant"):
        raise TypeError("Cannot assign to constant cell")
    if hcell["celltype"] != "structured":
        raise TypeError("Can only assign directly to properties of structured cells")
    ctx = cell._parent()
    if isinstance(value, Cell):
        assert (
            value._parent() is ctx
        )  # no connections between different (toplevel) contexts
        _remove_independent_mountshares(hcell)
        assign_connection(ctx, value._path, cell._path + path, False)
        ctx._translate()
    elif isinstance(value, ConstantTypes):
        check_libinstance_subcontext_binding(ctx, path)
        removed1 = ctx.remove_connections(
            cell._path + path, endpoint="link", match="all"
        )
        removed2 = ctx.remove_connections(
            cell._path + path, endpoint="target", match="all"
        )
        removed = removed1 or removed2
        untranslated = cell._get_hcell().get("UNTRANSLATED")
        if removed:
            ctx._translate()
        if untranslated:
            raise Exception(
                """This cell is untranslated.
You must first translate the cell before assigning constants to sub-values.
Run 'ctx.translate()' or 'await ctx.translation()'
"""
            )
        handle = cell.handle
        for p in path[:-1]:
            if isinstance(p, int):
                handle = handle[p]
            else:
                handle = getattr(handle, p)
        p = path[-1]
        if isinstance(p, int):
            handle[p] = value
        else:
            setattr(handle, p, value)
    else:
        raise TypeError(value)


def assign(ctx, path, value, *, help_context=False):
    from .Context import Context
    from .SubContext import SubContext
    from .library.libinstance import LibInstance
    from .library import Library, LibraryContainer
    from .library.include import IncludedLibrary, IncludedLibraryContainer
    from .Transformer import TransformerCopy

    ConstantTypes = getConstantTypes()

    nodedict = ctx._graph[0]
    if under_libinstance_control(nodedict, path):
        ok = False
        if path in nodedict:
            if nodedict[path]["type"] == "libinstance":
                if not under_libinstance_control(nodedict, path[:-1]):
                    ok = True
        if not ok:
            msg = "Cannot assign to path under libinstance control: {}"
            raise Exception(msg.format(path))
    if isinstance(value, (Library, LibraryContainer)):
        raise TypeError("Library must be included first")
    elif isinstance(value, (IncludedLibrary, IncludedLibraryContainer)):
        raise TypeError("Library must be instantiated first")
    elif isinstance(value, Transformer):
        if help_context:
            raise TypeError(type(value))
        if value._path is None:
            ctx.remove_connections(path, endpoint="target", match="all")
            value._init(ctx, path, set_node=True)
        else:
            assert value._parent() is not None
            value._assign_to(ctx, path)
    elif isinstance(value, Macro):
        if help_context:
            raise TypeError(type(value))
        value._init(ctx, path)
    elif isinstance(value, (Cell, DeepCellBase)):
        if value._parent() is None:
            cellnode = deepcopy(value._node)
            value._init(ctx, path)
            if isinstance(value, Cell):
                if cellnode is None:
                    if isinstance(value, FolderCell):
                        cellnode = get_new_foldercell(path)
                    else:
                        cellnode = get_new_cell(path)
                else:
                    cellnode["path"] = path
                if "celltype" not in cellnode:
                    if help_context:
                        cellnode["celltype"] = "text"
                    else:
                        cellnode["celltype"] = "structured"
            else:  # isinstance(value, DeepCellBase):
                if cellnode is None:
                    cellnode = type(value)._new_func(path)
                else:
                    cellnode["path"] = path
            ctx._graph.nodes[path] = cellnode
        else:
            assert value._get_top_parent() is ctx, value
            try:
                target = get_path(ctx, path, namespace=None, is_target=True)
            except AttributeError:
                target = None
            if isinstance(target, Cell):
                _remove_independent_mountshares(target._get_hcell())
            if target is None and isinstance(value, DeepCellBase):
                cellnode = type(value)._new_func(path)
                type(value)(parent=ctx, path=path)
                ctx._graph.nodes[path] = cellnode
            elif target is None and isinstance(value, FolderCell):
                cellnode = get_new_foldercell(path)
                ctx._graph.nodes[path] = cellnode

            assign_connection(ctx, value._path, path, True)
        ctx._translate()
    elif isinstance(value, (Resource, ConstantTypes)):
        v = value
        if isinstance(value, Resource):
            v = value.data
        creates_new_cell = assign_constant(ctx, path, v, help_context=help_context)
        if creates_new_cell:
            ctx._translate()
        else:
            check_libinstance_subcontext_binding(ctx, path)
        if isinstance(value, Resource):
            node = ctx._graph.nodes[path]
            if node["type"] != "cell":
                raise TypeError(node["type"])
            node["mount"] = {
                "path": value.filename,
                "mode": "r",
                "authority": "file",
                "persistent": True,
            }
    elif isinstance(value, (Context, SubContext)):
        assign_context(ctx, path, value)
        ctx._translate()
    elif isinstance(value, Module):
        if help_context:
            raise TypeError(type(value))
        if value._parent() is None:
            node = deepcopy(value._node)
            value._init(ctx, path)
            if node is None:
                node = get_new_module(path)
            else:
                node["path"] = path
            ctx._graph.nodes[path] = node
        else:
            assert value._get_top_parent() is ctx, value
            try:
                target = get_path(ctx, path, namespace=None, is_target=True)
            except AttributeError:
                target = None
            if isinstance(target, Cell):
                _remove_independent_mountshares(target._get_hcell())
            assign_connection(ctx, value._path, path, True)
            ctx._translate()
    elif isinstance(value, LibInstance):
        if help_context:
            raise TypeError(type(value))
        assign_libinstance(ctx, path, value)
        ctx._translate()
    elif callable(value):
        if help_context:
            raise TypeError("callable")
        if path in ctx._children:
            old = ctx._children[path]
            if isinstance(old, Cell):
                if old.celltype == "code":
                    result = assign_constant(ctx, path, value)
                    check_libinstance_subcontext_binding(ctx, path)
                    return result
        assign_transformer(ctx, path, value)
    elif isinstance(value, TransformerCopy):
        tf = value.transformer()
        if tf is None:
            raise Exception("Transformer no longer exists")
        assign_transformer_copy(ctx, path, tf)
    elif isinstance(value, (Proxy, SchemaWrapper)):
        assert value._parent()._parent() is ctx
        if path not in ctx._children:
            Cell(parent=ctx, path=path)  # inserts itself as child
            node = get_new_cell(path)
            if help_context:
                node["celltype"] = "text"
            else:
                node["celltype"] = "structured"
            ctx._graph[0][path] = node
        assign_connection(ctx, value._virtual_path, path, False)
        check_libinstance_subcontext_binding(ctx, path)
        ctx._translate()
    elif isinstance(value, Link):
        if help_context:
            raise TypeError(type(value))
        value._init(ctx, path)
        ctx._translate()
    elif isinstance(value, CompiledObjectDict):
        raise TypeError(
            "Cannot assign directly to all module objects; assign to individual elements"
        )
    elif isinstance(value, CompiledObjectWrapper):
        raise TypeError(
            "Cannot assign directly to an entire module object; assign to individual elements"
        )
    else:
        raise TypeError(str(value), type(value))


from ..midlevel.util import get_path
from .Base import Base
