import inspect

from . import ConstantTypes
from ..mixed import MixedBase
from ..silk import Silk
from .Cell import Cell
from .Transformer import Transformer

def assign_constant(ctx, path, value):
    if isinstance(value, (Silk, MixedBase)):
        raise NotImplementedError
    #TODO: run it through Silk or something, to check that there aren't lists/dicts/tuples-of-whatever-custom-classes
    # not sure if tuple is natively accepted too
    ctx._children[path] = Cell(ctx, path)
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
    ctx._children[path] = Transformer(ctx, path)

def assign(ctx, path, value):
    if callable(value):
        assign_transformer(ctx, path, value)
    elif isinstance(value, Transformer):
        value._assign_to(ctx, path)
    elif isinstance(value, ConstantTypes):
        assign_constant(ctx, path, value)
    else:
        raise TypeError(value)
