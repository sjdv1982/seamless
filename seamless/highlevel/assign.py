import inspect

from . import ConstantTypes
from ..mixed import MixedBase
from ..silk import Silk
from .Cell import Cell
from .pin import InputPin, OutputPin
from .Transformer import Transformer

def assign_constant(ctx, path, value):
    if isinstance(value, (Silk, MixedBase)):
        raise NotImplementedError
    #TODO: run it through Silk or something, to check that there aren't lists/dicts/tuples-of-whatever-custom-classes
    # not sure if tuple is natively accepted too
    if path in ctx._children:
        old = ctx._children[path]
        if isinstance(old, Cell):
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
    ctx._graph[0][path] = cell
    return True

def assign_transformer(ctx, path, func):
    parameters = list(inspect.signature(func).parameters.keys())
    transformer =    {
        "path": path,
        "type": "transformer",
        "language": "python",
        "code": inspect.getsource(func),
        "pins": {param:{"submode": "silk"} for param in parameters},
        "values": {},
        "RESULT": "result",
        "INPUT": "inp",
        "with_schema": False,
        "buffered": True,
        "plain": False,
        "plain_result": False,
    }
    ctx._graph[0][path] = transformer
    Transformer(ctx, path) #inserts itself as child

def assign_connection(ctx, source, target):
    if target not in ctx._children:
        assign_constant(ctx, target, None)
    assert source in ctx._children, source
    s, t = ctx._children[source], ctx._children[target]
    assert isinstance(s, (Cell, OutputPin))
    assert isinstance(t, (Cell, InputPin))
    if s._virtual_path is not None:
        source = s._virtual_path
    if t._virtual_path is not None:
        target = t._virtual_path
    connection = {
        "type": "connection",
        "source": source,
        "target": target
    }
    ctx._graph[1].append(connection)


def assign(ctx, path, value):
    if callable(value):
        assign_transformer(ctx, path, value)
        ctx._translate()
    elif isinstance(value, Transformer):
        value._assign_to(ctx, path)
    elif isinstance(value, Cell):
        assign_connection(value._parent(), value._path, path)
        ctx._translate()
    elif isinstance(value, ConstantTypes):
        new_cell = assign_constant(ctx, path, value)
        if new_cell:
            ctx._translate()
    else:
        raise TypeError(value)
