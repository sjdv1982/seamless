import inspect
from copy import deepcopy
import json
import weakref
from types import LambdaType

from . import ConstantTypes
from ..mixed import MixedBase
from ..silk import Silk
from .Cell import Cell
from .pin import InputPin, OutputPin
from .Transformer import Transformer
from ..midlevel import copy_context
from . import assign_virtual
from ..core.lambdacode import lambdacode

def assign_constant(ctx, path, value):
    if isinstance(value, (Silk, MixedBase)):
        raise NotImplementedError
    #TODO: run it through Silk or something, to check that there aren't lists/dicts/tuples-of-whatever-custom-classes
    # not sure if tuple is natively accepted too
    if path in ctx._children:
        old = ctx._children[path]
        if isinstance(old, Cell):
            old._set(value)
            return False
        raise AttributeError(path) #already exists
    Cell(ctx, path) #inserts itself as child
    cell = {
        "path": path,
        "type": "cell",
        "celltype": "structured",
        "format": "mixed",
        "silk": True,
        "buffered": True,
        "value": value,
        "schema": None,
    }
    ### json.dumps(cell)
    ctx._graph[0][path] = cell
    return True

def assign_transformer(ctx, path, func):
    if path in ctx._children:
        old = ctx._children[path]
        if isinstance(old, Cell):
            old.set(func)
            return
        raise AttributeError(path) #already exists
    parameters = []
    for pname, p in inspect.signature(func).parameters.items():
        #TODO: look at default parameters, make them optional
        if p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL):
            parameters.append(pname)
    code = inspect.getsource(func)
    #if isinstance(func, LambdaType): ### does not work, bug in Python??
    if func.__class__.__name__ == "lambda":
        print("FUNC!", func)
        code = lambdacode(func)
        if code is None:
            raise ValueError("Cannot extract source code from this lambda")

    transformer =    {
        "path": path,
        "type": "transformer",
        "language": "python",
        "code": code,
        "pins": {param:{"submode": "silk"} for param in parameters},
        "values": {},
        "RESULT": "result",
        "INPUT": "inp",
        "with_schema": False,
        "buffered": True,
        "plain": False,
        "plain_result": False,
    }
    ### json.dumps(transformer)
    ctx._graph[0][path] = transformer
    Transformer(ctx, path) #inserts itself as child

def assign_connection(ctx, source, target, standalone_target):
    if standalone_target and target not in ctx._children:
        assign_constant(ctx, target, None)
    assert source in ctx._children, source
    s = ctx._children[source]
    assert isinstance(s, (Cell, OutputPin))
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


def _assign_context(ctx, new_nodes, new_connections, path):
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
    for p, node in new_nodes.items():
        pp = path + p
        node["path"] = pp
        nodes[pp] = node
        nodetype = node["type"]
        if nodetype == "cell":
            Cell(ctx, pp)
        elif nodetype == "transformer":
            Transformer(ctx, pp)
        elif nodetype == "context":
            pass
        else:
            raise TypeError(nodetype)
    for con in new_connections:
        con["source"] = path + con["source"]
        con["target"] = path + con["target"]
        connections.append(con)

def assign_context(ctx, path, value):
    assert not ctx._parent()._as_lib
    new_ctx = value
    new_nodes, new_connections = new_ctx._get_graph()
    _assign_context(ctx, new_nodes, new_connections, path)
    subcontexts = ctx._graph.subcontexts
    ctx._del_subcontext(path)
    as_lib = new_ctx._as_lib
    if as_lib is not None:
        if path not in subcontexts:
            subcontexts[path] = {}
        subcontexts[path]["from_lib"] = as_lib.name
        as_lib.copy_deps.add((weakref.ref(ctx), path))
    ctx._needs_translation = True

def assign(ctx, path, value):
    from .Context import Context, SubContext
    # TODO: assign_virtual, different assign if path is virtual (generated by highlevel macro)
    if isinstance(value, Transformer):
        value._assign_to(ctx, path)
    elif isinstance(value, Cell):
        assert value._parent() is ctx
        assign_connection(ctx, value._path, path, True)
        ctx._translate()
    elif isinstance(value, ConstantTypes):
        new_cell = assign_constant(ctx, path, value)
        if new_cell:
            ctx._translate()
    elif isinstance(value, (Context, SubContext)):
        assign_context(ctx, path, value)
        ctx._translate()
    elif callable(value):
        assign_transformer(ctx, path, value)
        ctx._translate()
    else:
        raise TypeError(value)
    ### g = {".".join(k): v for k,v in ctx._graph[0].items()}
    ### json.dumps([g, ctx._graph[1]])
