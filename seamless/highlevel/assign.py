import inspect
from copy import deepcopy
import json
import weakref

from . import ConstantTypes
from ..mixed import MixedBase
from ..silk import Silk
from .Cell import Cell, get_new_cell
from .Resource import Resource
from .pin import PinWrapper
from .Transformer import Transformer
from .Reactor import Reactor
from .Macro import Macro
from .proxy import Proxy, CodeProxy, HeaderProxy
from ..midlevel import copying
from . import parse_function_code
from .Link import Link
from .compiled import CompiledObjectDict, CompiledObjectWrapper
from .SchemaWrapper import SchemaWrapper


def under_libinstance_control(nodedict, path):
    lp = len(path)
    if path in nodedict:
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
    return node["type"] == "libinstance"

def assign_constant(ctx, path, value):
    ###if isinstance(value, (Silk, MixedBase)):
    ###    raise NotImplementedError
    #TODO: run it through Silk or something, to check that there aren't lists/dicts/tuples-of-whatever-custom-classes
    # not sure if tuple is natively accepted too
    old = None
    if path in ctx._children:
        old = ctx._children[path]
        if isinstance(old, Cell):
            removed = ctx._remove_connections(path, keep_links=True)
            if removed:
                ctx._translate()
            hcell = old._get_hcell()
            if not hcell.get("UNTRANSLATED"):
                cell = old._get_cell()
                if cell.has_authority():
                    old._set(value)
                    return False
        else:
            raise AttributeError(path) #already exists, but not a Cell
    if old is None:
        child = Cell(parent=ctx, path=path) #inserts itself as child
        cell = get_new_cell(path)
    else:
        cell = old._get_hcell()
    if callable(value):
        code, _, _ = parse_function_code(value)
        if old is None:
            cell.celltype = "python"
            value = code
        elif old.celltype in ("python", "ipython"):
            value = code

    cell["TEMP"] = value
    ### json.dumps(cell)
    ctx._graph[0][path] = cell
    ctx._translate()

def assign_resource(ctx, path, value):
    result = assign_constant(value.data)
    child = ctx._children[path]
    child.mount(value.filename)

def assign_transformer(ctx, path, func):
    from .Transformer import default_pin
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
        #TODO: look at default parameters, make them optional
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
        tf = Transformer(
            parent=ctx,
            path=path,
            code=code,
            pins=parameters
        ) #inserts itself as child
        assert ctx._children[path] is tf
        ctx._translate()

def assign_libinstance(ctx, path, libinstance):
    libinstance._bind(ctx, path)


def assign_connection(ctx, source, target, standalone_target, exempt=[]):
    nodedict = ctx._graph[0]
    if under_libinstance_control(nodedict, source):
        msg = "Cannot connect from path under libinstance control: {}"
        raise Exception(msg.format(source))
    if under_libinstance_control(nodedict, target):
        msg = "Cannot connect to path under libinstance control: {}"
        raise Exception(msg.format(target))
    if standalone_target:
        if target not in ctx._children:
            assign_constant(ctx, target, None)
        t = ctx._children[target]
        assert isinstance(t, Cell)
        hcell = t._get_hcell()
        if "TEMP" in hcell:
            hcell.pop("TEMP")
        elif "checksum" in hcell:
            hcell["checksum"].pop("value", None)
            hcell["checksum"].pop("auth", None)
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
        if target[:len(ctarget)] != ctarget:
            return True
        for e in exempt:
            if ctarget[:len(e)] == e:
                return True
        return False
    ctx._graph[1][:] = filter(keep_con, ctx._graph[1])
    if standalone_target:
        t = ctx._children[target]
        assert not t.get_links()
    assert source in ctx._children or source[:-1] in ctx._children, source
    s = None
    if source in ctx._children:
        s = ctx._children[source]
        if isinstance(s, Cell):
            hcell = s._get_hcell()
            if hcell.get("constant"):
                raise TypeError("Cannot assign to constant cell")
        else:
            raise TypeError(type(s))
    else:
        source_parent_path = source[:-1]
        if source_parent_path not in ctx._children:
            raise KeyError("Unknown path '{}'".format(source_parent_path))
        source_parent = ctx._children[source_parent_path]
        assert isinstance(source_parent, (Transformer, Reactor, Macro)), source_parent
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
            elif isinstance(source_parent, Transformer) \
              and attr == source_parent.RESULT:
                source = source_parent_path
                s = None
            elif attr in source_parent.pins:
                pin = source_parent.pins[attr]
                if isinstance(source_parent, Macro):
                    assert pin["io"] == "output", (source, pin["io"])
                elif isinstance(source_parent, Reactor):
                    assert pin["io"] in ("output", "edit"), (source, pin["io"])
            else:
                raise TypeError("No output pin '{}'".format(attr))
    if s is not None and s._virtual_path is not None:
        source = s._virtual_path
    if standalone_target:
        t = ctx._children[target]
        assert isinstance(t, Cell)
        if t._virtual_path is not None:
            target = t._virtual_path
    connection = {
        "type": "connection",
        "source": source,
        "target": target
    }
    ctx._graph[1].append(connection)

def _assign_context2(ctx, new_nodes, new_connections, path, runtime):
    from .Context import Context
    from .Cell import Cell
    from .Transformer import Transformer
    assert isinstance(ctx, Context)
    nodes, connections, _, _ = ctx._graph
    if runtime:
        nodes, connections, _, _ = ctx._runtime_graph
    for p in list(nodes.keys()):
        if p[:len(path)] == path:
            nodes.pop(p)
    for con in list(connections):
        if con["type"] == "connection":
            source, target = con["source"], con["target"]
            if source[:len(path)] != path:
                continue
            if target[:len(path)] != path:
                continue
            connections.remove(con)
    nodes[path] = {
        "path": path,
        "type": "context"
    }
    new_nodes = deepcopy(new_nodes)
    new_connections = deepcopy(new_connections)
    targets = set()
    for con in new_connections:
        targets.add(con["target"])
    for node in new_nodes:
        old_path = node["path"]
        pp = path + old_path
        node["path"] = pp
        nodetype = node["type"]
        nodes[pp] = node
        if not runtime:
            node["UNTRANSLATED"] = True
        remove_checksum = []
        if nodetype == "cell":
            Cell(parent=ctx, path=pp)
            ###remove_checksum.append("temp")
            if node["celltype"] == "structured":
                remove_checksum.append("value")
                remove_checksum.append("buffer")
            else: # simple cell, can be targeted at most once
                if old_path in targets:
                    remove_checksum.append("value")
        elif nodetype == "transformer":
            Transformer(parent=ctx, path=pp)
            remove_checksum += ["input_temp", "input", "input_buffer", "result"]
            potential = ("code", "schema", "result_schema", "main_module")
            for pot in potential:
                if old_path + (pot,) in targets:
                    remove_checksum.append(pot)
            if runtime:
                node.pop("UNTRANSLATED", None)
        elif nodetype == "macro":
            Macro(parent=ctx, path=pp)
            remove_checksum += ["param_temp", "param", "param_buffer"]
            potential = ("code", "schema")
            for pot in potential:
                if old_path + (pot,) in targets:
                    remove_checksum.append(pot)
            if runtime:
                node.pop("UNTRANSLATED", None)
        elif nodetype == "context":
            pass
        else:
            raise TypeError(nodetype)
        if "checksum" in node:
            cs = node["checksum"]
            for item in remove_checksum:
                cs.pop(item, None)
    for con in new_connections:
        con["source"] = path + con["source"]
        con["target"] = path + con["target"]
        connections.append(con)

def _assign_context(ctx, new_nodes, new_connections, path, runtime):
    if runtime:
        old_graph = deepcopy(ctx._graph)
    ctx._destroy_path(path, runtime=runtime)
    _assign_context2(ctx, new_nodes, new_connections, path, runtime)
    graph = ctx._runtime_graph if runtime else ctx._graph
    subctx = graph.nodes[path]
    assert subctx["type"] == "context", path
    ctx._translate()
    if runtime:
        graph2 = deepcopy(ctx._graph)
        assert old_graph == graph2

def assign_context(ctx, path, value):
    graph = value.get_graph()
    new_nodes, new_connections = graph["nodes"], graph["connections"]
    _assign_context(ctx, new_nodes, new_connections, path, runtime=False)

def assign_to_subcell(cell, path, value):
    from ..core.structured_cell import StructuredCell
    hcell = cell._get_hcell()
    if hcell.get("constant"):
        raise TypeError("Cannot assign to constant cell")
    if hcell["celltype"] != "structured":
        raise TypeError("Can only assign directly to properties of structured cells")
    ctx = cell._parent()
    if isinstance(value, Cell):
        assert value._parent() is ctx #no connections between different (toplevel) contexts
        assign_connection(ctx, value._path, cell._path + path, False)
        ctx._translate()
    elif isinstance(value, ConstantTypes):
        removed = ctx._remove_connections(cell._path + path)
        if removed:
            ctx._translate()
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


def assign(ctx, path, value):
    from .Context import Context, SubContext
    from .library.libinstance import LibInstance
    from .library import Library, LibraryContainer
    from .library.include import IncludedLibrary, IncludedLibraryContainer
    from .proxy import Proxy
    nodedict = ctx._graph[0]
    if under_libinstance_control(nodedict, path):
        msg = "Cannot assign to path under libinstance control: {}"
        raise Exception(msg.format(path))
    if isinstance(value, (Library, LibraryContainer)):
        raise TypeError("Library must be included first")
    if isinstance(value, (IncludedLibrary, IncludedLibraryContainer)):
        raise TypeError("Library must be instantiated first")
    if isinstance(value, Transformer):
        if value._path is None:
            value._init(ctx, path)
        else:
            value._assign_to(ctx, path)
    elif isinstance(value, Macro):
        value._init(ctx, path)
    elif isinstance(value, Cell):
        if value._parent() is None:
            value._init(ctx, path)
            cellnode = deepcopy(value._node)
            if cellnode is None:
                cellnode = get_new_cell(path)
            else:
                cellnode["path"] = path
            ctx._graph.nodes[path] = cellnode
        else:
            assert value._get_top_parent() is ctx, value
            assign_connection(ctx, value._path, path, True)
        ctx._translate()
    elif isinstance(value, (Resource, ConstantTypes)):
        v = value
        if isinstance(value, Resource):
            v = value.data
        new_cell = assign_constant(ctx, path, v)
        if new_cell:
            ctx._translate()
        if isinstance(value, Resource):
            node = ctx._graph.nodes[path]
            node["mount"] = {
                "path": value.filename,
                "mode": "r",
                "authority": "file",
                "persistent": True,
            }
    elif isinstance(value, (Context, SubContext)):
        assign_context(ctx, path, value)
        ctx._translate()
    elif isinstance(value, LibInstance):
        assign_libinstance(ctx, path, value)
        ctx._translate()
    elif callable(value):
        if path in ctx._children:
            old = ctx._children[path]
            if isinstance(old, Cell):
                if old.celltype == "code":
                    return assign_constant(ctx, path, value)
        assign_transformer(ctx, path, value)
    elif isinstance(value, (Proxy, SchemaWrapper)):
        assert value._parent()._parent() is ctx
        if path not in ctx._children:
            Cell(parent=ctx, path=path) #inserts itself as child
            node = get_new_cell(path)
            ctx._graph[0][path] = node
        #TODO: break links and connections from ctx._children[path]
        assign_connection(ctx, value._virtual_path, path, False)
        ctx._translate()
    elif isinstance(value, Link):
        value._init(ctx, path)
        ctx._translate()
    elif isinstance(value, CompiledObjectDict):
        raise TypeError("Cannot assign directly to all module objects; assign to individual elements")
    elif isinstance(value, CompiledObjectWrapper):
        raise TypeError("Cannot assign directly to an entire module object; assign to individual elements")
    else:
        raise TypeError(str(value), type(value))
