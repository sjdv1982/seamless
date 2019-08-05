def propagate_accessor(livegraph, accessor, void):    
    accessor._void = void
    target = accessor.write_accessor.target()
    if isinstance(target, Cell):
        if accessor.write_accessor.path is None:
            if void:
                manager = target._get_manager()
                manager.cancel_cell(target, None, True)
            else:
                propagate_simple_cell(livegraph, target)
        else:
            raise NotImplementedError # livegraph branch
    elif isinstance(target, Transformer):
        propagate_transformer(livegraph, target)
    else:
        raise TypeError(target)

def propagate_simple_cell(livegraph, cell):    
    assert cell._monitor is None
    if cell._void:
        cell._void = False
    for accessor in livegraph.cell_to_downstream[cell]:
        propagate_accessor(livegraph, accessor, void=False)

def propagate_cell(livegraph, cell):
    if cell._monitor is not None:
        raise NotImplementedError # livegraph branch
    return propagate_simple_cell(livegraph, cell)

def propagate_transformer(livegraph, transformer):
    if transformer._void:
        return
    manager = transformer._get_manager()
    TransformerUpdateTask(manager, transformer).launch()

def propagate_reactor(livegraph, reactor):
    if reactor._void:
        return
    raise NotImplementedError # livegraph branch

from ..cell import Cell
from ..transformer import Transformer
from ..reactor import Reactor
from ..macro import Macro
from ..status import StatusReasonEnum
from ..manager.tasks.transformer_update import TransformerUpdateTask