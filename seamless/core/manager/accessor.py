import weakref

class Accessor:
    pass

class ReadAccessor(Accessor):
    _checksum = None
    _void = True
    _status_reason = None
    def __init__(self, manager, path, celltype):
        self.manager = weakref.ref(manager)
        self.path = path
        assert celltype in celltypes or isinstance(celltype, MacroPath)
        self.reactor_pinname = None
        self.celltype = celltype   
        self.write_accessor = None
        self.expression = None
        self._status_reason = StatusReasonEnum.UNDEFINED
    
    def build_expression(self, livegraph, checksum):
        """Returns if expression has changed"""
        celltype = self.celltype
        if isinstance(celltype, MacroPath):
            macropath = celltype
            if macropath._cell is None:
                self._clear_expression(livegraph)
                return
            celltype = macropath._cell._celltype
        target_celltype = self.write_accessor.celltype
        target_subcelltype = self.write_accessor.subcelltype
        if isinstance(target_celltype, MacroPath):
            macropath = target_celltype
            if macropath._cell is None:
                self._clear_expression(livegraph)
                return
            target_celltype = macropath._cell._celltype
            target_subcelltype = macropath._cell._subcelltype
        target_cell_path = None
        target = self.write_accessor.target
        if isinstance(target, Cell):
            target_cell_path = str(cell)
        expression = Expression(
            checksum, self.path, celltype,
            target_celltype,
            target_subcelltype, 
            target_cell_path=target_cell_path
        )
        if self.expression is not None:
            if expression == self.expression:
                return False
            livegraph.decref_expression(self.expression, self)
        self.expression = expression
        livegraph.incref_expression(expression, self)
        return True

    def _clear_expression(self, livegraph):
        if self.expression is None:
            return
        livegraph.decref_expression(self.expression, self)
        self.expression = None

class WriteAccessor(Accessor):
    def __init__(self, read_accessor, target, celltype, subcelltype, pinname, path):
        from ...core.cell import Cell
        from ...core.worker import Worker
        assert isinstance(read_accessor, ReadAccessor)
        assert isinstance(target, (Cell, Worker))
        assert pinname is None or path is None
        self.read_accessor = weakref.ref(read_accessor)
        self.target = weakref.ref(target)
        assert celltype in celltypes or isinstance(celltype, MacroPath)
        self.celltype = celltype
        assert subcelltype is None or subcelltype in subcelltypes 
        self.subcelltype = subcelltype
        self.pinname = pinname
        self.path = path

from ...core.cell import Cell, celltypes, subcelltypes
from ...core.macro import Path as MacroPath
from ...core.status import StatusReasonEnum
from .expression import Expression