def propagate_accessor(livegraph, accessor, void):    
    accessor._void = void
    target = accessor.write_accessor.target()
    if isinstance(target, Cell):
        if accessor.write_accessor.path is None:
            if void:
                target._status_reason = StatusReasonEnum.UPSTREAM
            propagate_simple_cell(livegraph, target, void)
        else:
            raise NotImplementedError # livegraph branch
    else:
        raise TypeError(target)

def propagate_simple_cell(livegraph, cell, void):
    assert cell._monitor is None
    cell._void = void
    for accessor in livegraph.cell_to_downstream[cell]:
        if accessor._void != void:
            propagate_accessor(livegraph, accessor, void)

def propagate_cell(livegraph, cell, void):
    if cell._monitor is not None:
        raise NotImplementedError # livegraph branch
    return propagate_simple_cell(livegraph, cell, void)

def propagate_transformer(livegraph, transformer, void):
    if void:
        transformer._void = void
    if transformer._void:
        void = True
    for accessor in livegraph.transformer_to_downstream[transformer]:
        propagate_accessor(livegraph, accessor, void)

def propagate_reactor(livegraph, transformer, void):
    raise NotImplementedError # livegraph branch

from ..cell import Cell
from ..transformer import Transformer
from ..reactor import Reactor
from ..macro import Macro
from ..status import StatusReasonEnum