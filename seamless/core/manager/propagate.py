
def _propagate_cell_accessor(livegraph, accessor, target, void):
    if accessor.write_accessor.path is None:
        if void:
            manager = target._get_manager()
            manager.cancel_cell(target, None, True)
        else:
            propagate_simple_cell(livegraph, target)
    else:
        raise NotImplementedError # livegraph branch

def propagate_accessor(livegraph, accessor, void):    
    accessor._void = void
    target = accessor.write_accessor.target()    
    if isinstance(target, Cell):
        _propagate_cell_accessor(livegraph, accessor, target, void)
    elif isinstance(target, Transformer):
        propagate_transformer(livegraph, target)
    elif isinstance(target, Reactor):
        propagate_reactor(livegraph, target)
    elif isinstance(target, Macro):
        propagate_macro(livegraph, target)
    elif isinstance(target, MacroPath):
        if target._cell is not None:
            _propagate_cell_accessor(
                livegraph, accessor, target._cell, void
            )
    else:
        raise TypeError(target)

def propagate_simple_cell(livegraph, cell):    
    assert cell._monitor is None
    if cell._void:
        cell._void = False
    for accessor in livegraph.cell_to_downstream[cell]:
        propagate_accessor(livegraph, accessor, void=False)
    if cell._paths is not None:
        for macropath in cell._paths:
            pmacro = macropath._macro
            if pmacro is None:
                fullpath = macropath._path
            else:
                fullpath = pmacro.path + ("ctx",) + macropath._path
            #assert fullpath == cell.path, (fullpath, cell.path)  # no, because of links...
            for accessor in livegraph.macropath_to_downstream[macropath]:
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
    manager = reactor._get_manager()
    ReactorUpdateTask(manager, reactor).launch()

def propagate_macro(livegraph, macro):
    if macro._void:
        return
    if macro._gen_context is not None:
        macro._gen_context.destroy()
        macro._gen_context = None
    manager = macro._get_manager()
    MacroUpdateTask(manager, macro).launch()

from ..cell import Cell
from ..transformer import Transformer
from ..reactor import Reactor
from ..macro import Macro, Path as MacroPath
from ..status import StatusReasonEnum
from ..manager.tasks.transformer_update import TransformerUpdateTask
from ..manager.tasks.reactor_update import ReactorUpdateTask
from ..manager.tasks.macro_update import MacroUpdateTask