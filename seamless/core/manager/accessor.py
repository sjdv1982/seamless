import weakref

class Accessor:
    pass

class ReadAccessor(Accessor):
    _checksum = None
    _void = False
    def __init__(self, manager, path, celltype):
        self.manager = weakref.ref(manager)
        self.path = path
        assert celltype in celltypes
        self.celltype = celltype   
        self.write_accessor = None
        self.expression = None
    
    def build_expression(self, livegraph, checksum):
        """Returns if expression has changed"""
        expression = Expression(
            checksum, self.path, self.celltype, 
            self.write_accessor.celltype,
            self.write_accessor.subcelltype
        )
        if self.expression is not None:
            if expression.get_hash() == self.expression.get_hash():
                return False
            livegraph.decref_expression(self.expression, self)
        self.expression = expression
        livegraph.incref_expression(expression, self)
        return True


class WriteAccessor(Accessor):
    def __init__(self, read_accessor, target, celltype, subcelltype, pinname, path):
        from ...core.cell import Cell
        from ...core.worker import Worker
        assert isinstance(read_accessor, ReadAccessor)
        assert isinstance(target, (Cell, Worker))
        assert pinname is None or path is None
        self.read_accessor = weakref.ref(read_accessor)
        self.target = weakref.ref(target)
        self.celltype = celltype
        assert subcelltype is None or subcelltype in subcelltypes 
        self.subcelltype = subcelltype
        self.pinname = pinname
        self.path = path

from ...core.cell import celltypes, subcelltypes
from .expression import Expression