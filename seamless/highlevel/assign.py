import inspect
from copy import deepcopy
import json
import weakref

from . import ConstantTypes
from ..mixed import MixedBase
from ..silk import Silk
from .Cell import Cell
from .Resource import Resource
from .pin import InputPin, OutputPin
from .Transformer import Transformer
from .Reactor import Reactor
from .proxy import Proxy, CodeProxy
from ..midlevel import copying
from . import parse_function_code
from .Link import Link
from .compiled import CompiledObjectDict, CompiledObjectWrapper

def get_new_cell(path):
    return {
        "path": path,
        "type": "cell",
        "celltype": "structured",
        "datatype": "mixed",
        "silk": True,
        "buffered": True,
        "UNTRANSLATED": True,
    }


def assign_constant(ctx, path, value):
    ###if isinstance(value, (Silk, MixedBase)):
    ###    raise NotImplementedError
    #TODO: run it through Silk or something, to check that there aren't lists/dicts/tuples-of-whatever-custom-classes
    # not sure if tuple is natively accepted too
    if path in ctx._children:
        old = ctx._children[path]
        if isinstance(old, Cell):
            old._set(value)
            ctx._remove_connections(path)
            return False
        raise AttributeError(path) #already exists, but not a Cell
    child = Cell(ctx, path) #inserts itself as child
    cell = get_new_cell(path)
    cell["TEMP"] = value
    ### json.dumps(cell)
    ctx._graph[0][path] = cell
    return True

def assign_resource(ctx, path, value):
    result = assign_constant(value.data)
    child = ctx._children[path]
    child.mount(value.filename)

def assign_transformer(ctx, path, func):
    from .Transformer import default_pin
    if path in ctx._children:
        old = ctx._children[path]
        if isinstance(old, Cell):
            old.set(func)
        else:
            ctx._destroy_path(path)

    assert callable(func)
    code, _, _ = parse_function_code(func)
    parameters = []
    for pname, p in inspect.signature(func).parameters.items():
        #TODO: look at default parameters, make them optional
        if p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL):
            parameters.append(pname)
    Transformer(ctx, path, code, parameters) #inserts itself as child

def assign_connection(ctx, source, target, standalone_target, exempt=[]):
    if standalone_target:
        if target not in ctx._children:
            assign_constant(ctx, target, None)
        t = ctx._children[target]
        assert isinstance(t, Cell)
        hcell = t._get_hcell()
        if hcell["celltype"] == "structured":
            hcell.pop("stored_state", None)
            hcell.pop("cached_state", None)
        else:
            hcell.pop("stored_value", None)
            hcell.pop("cached_value", None)
    lt = len(target)
    def keep_con(con):
        ctarget = con["target"]
        if ctarget[:lt] != target:
            return True
        for e in exempt:
            if ctarget[:len(e)] == e:
                return True
        return False
    ctx._graph[1][:] = filter(keep_con, ctx._graph[1])
    if standalone_target:
        t = ctx._children[target]
        assert not t.links
    assert source in ctx._children or source[:-1] in ctx._children, source
    if source in ctx._children:
        s = ctx._children[source]
        assert isinstance(s, (Cell, OutputPin))
    else:
        source_parent = ctx._children[source[:-1]]
        assert isinstance(source_parent, (Transformer, Reactor))
        attr = source[-1]
        s = getattr(source_parent, attr)
        assert isinstance(s, Proxy)
        if not isinstance(s, CodeProxy):
            assert isinstance(source_parent, Reactor)
            pin = source_parent.pins[attr]
            assert pin["io"] in ("output", "edit"), (source, pin["io"])
    if s._virtual_path is not None:
        source = s._virtual_path
    if standalone_target:
        t = ctx._children[target]
        assert isinstance(t, (Cell, InputPin))
        if t._virtual_path is not None:
            target = t._virtual_path
    connection = {
        "type": "connection",
        "source": source,
        "target": target
    }
    ctx._graph[1].append(connection)


def _assign_context2(ctx, new_nodes, new_connections, path):
    from .Context import Context
    from .Cell import Cell
    from .Transformer import Transformer
    assert isinstance(ctx, Context)
    nodes, connections, _ = ctx._graph
    for p in list(nodes.keys()):
        if p[:len(path)] == path:
            nodes.pop(p)
    for con in list(connections):
        source, target = con["source"], con["target"]
        if source[:len(path)] != path:
            continue
        if target[:len(path)] != path:
            continue
        connections.remove(con)
    ctx._graph[0][path] = {
        "path": path,
        "type": "context"
    }
    new_nodes = deepcopy(new_nodes)
    new_connections = deepcopy(new_connections)
    for node in new_nodes:
        pp = path + node["path"]
        node["path"] = pp
        nodetype = node["type"]
        node["UNTRANSLATED"] = True
        if nodetype == "cell":
            Cell(ctx, pp)
        elif nodetype == "transformer":
            Transformer(ctx, pp)
        elif nodetype == "context":
            pass
        else:
            raise TypeError(nodetype)
        nodes[pp] = node
    for con in new_connections:
        con["source"] = path + con["source"]
        con["target"] = path + con["target"]
        connections.append(con)

def _assign_context(ctx, new_nodes, new_connections, path, from_lib):
    ctx._destroy_path(path)
    _assign_context2(ctx, new_nodes, new_connections, path)
    subctx = ctx._graph.nodes[path]
    assert subctx["type"] == "context", path
    if from_lib is not None:
        subctx["from_lib"] = from_lib.name
        from_lib.copy_deps.add((weakref.ref(ctx), path))
    ctx._translate()

def assign_context(ctx, path, value):
    new_ctx = value
    graph = new_ctx.get_graph()
    new_nodes, new_connections = graph["nodes"], graph["connections"]
    from_lib = new_ctx._as_lib
    _assign_context(ctx, new_nodes, new_connections, path, from_lib)

def assign_to_subcell(cell, path, value):
    from ..midlevel.copying import fill_cell_value
    hcell = cell._get_hcell()
    if hcell["celltype"] != "structured":
        raise TypeError("Can only assign directly to properties of structured cells")
    if isinstance(value, Cell):
        ctx = cell._parent()
        assert value._parent() is ctx #no connections between different (toplevel) contexts
        assign_connection(ctx, value._path, cell._path + path, False)
        ctx._translate()
    elif isinstance(value, ConstantTypes):
        structured_cell = cell._get_cell()
        if structured_cell._is_silk:
            handle = structured_cell.handle
            for p in path[:-1]:
                handle = getattr(handle, p)
            setattr(handle, path[-1], value)
        else:
            structured_cell.monitor.set_path(path, value)
        fill_cell_value(structured_cell, cell._get_hcell())
        cell._parent()._remount_graph()
    else:
        raise TypeError(value)


def assign_library_context_instance(ctx, path, lci):
    libname = lci.libname
    depsgraph = ctx._depsgraph
    dep = depsgraph.construct_library(libname, path, lci.args, lci.kwargs)
    depsgraph.evaluate_dep(dep)


def assign(ctx, path, value):
    from .Context import Context, SubContext, LibraryContextInstance
    from .proxy import Proxy
    if isinstance(value, Transformer):
        value._assign_to(ctx, path)
    elif isinstance(value, Cell):
        if value._parent is None:
            value._init(ctx, path)
            cell = get_new_cell(path)
            ctx._graph.nodes[path] = cell
        else:
            assert value._parent() is ctx
            assign_connection(ctx, value._path, path, True)
        ctx._translate()
    elif isinstance(value, (Resource, ConstantTypes)):
        v = value
        if isinstance(value, Resource):
            v = value.data
        new_cell = assign_constant(ctx, path, v)
        if new_cell:
            ctx._translate()
        else:
            old_len = len(ctx._graph[1])
            lp = len(path)
            ctx._graph[1][:] = [con for con in ctx._graph[1] if con["target"][:lp] != path]
            new_len = len(ctx._graph[1])
            if new_len < old_len:
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
    elif callable(value):
        done = False
        if path in ctx._children:
            old = ctx._children[path]
            if isinstance(old, Cell):
                old._set(value)
                done = True
        if not done:
            assign_transformer(ctx, path, value)
            ctx._translate()
    elif isinstance(value, Proxy):
        assert value._parent()._parent() is ctx
        if path not in ctx._children:
            Cell(ctx, path) #inserts itself as child
            node = get_new_cell(path)
            ctx._graph[0][path] = node
        #TODO: break links and connections from ctx._children[path]
        assign_connection(ctx, value._virtual_path, path, False)
        ctx._translate()
    elif isinstance(value, Link):
        value._init(ctx, path)
        ctx._translate()
    elif isinstance(value, LibraryContextInstance):
        assign_library_context_instance(ctx, path, value)
        ctx._translate()
    elif isinstance(value, CompiledObjectDict):
        raise TypeError("Cannot assign directly to all module objects; assign to individual elements")
    elif isinstance(value, CompiledObjectWrapper):
        raise TypeError("Cannot assign directly to an entire module object; assign to individual elements")
    else:
        raise TypeError(str(value), type(value))
    ### g = {".".join(k): v for k,v in ctx._graph[0].items()}
    ### json.dumps([g, ctx._graph[1]])
