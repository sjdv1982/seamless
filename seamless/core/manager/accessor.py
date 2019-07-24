import weakref

class Accessor:
    pass

class ReadAccessor(Accessor):
    _void = False
    def __init__(self, manager, path, celltype, subcelltype=None):
        self.manager = weakref.ref(manager)
        self.path = path
        assert celltype in celltypes
        self.celltype = celltype   
        assert subcelltype is None or subcelltype in subcelltypes 
        self.subcelltype = subcelltype
        self.write_accessor = None
        self.expression = None
    
    def build_expression(self, livegraph, checksum):
        expression = Expression(
            checksum, self.path, self.celltype, self.subcelltype
        )
        self.expression = expression
        livegraph.incref_expression(expression, self)


class WriteAccessor(Accessor):
    def __init__(self, read_accessor, target, pinname, path):
        from ...core.cell import Cell
        from ...core.worker import Worker
        assert isinstance(read_accessor, ReadAccessor)
        assert isinstance(target, (Cell, Worker))
        assert pinname is None or path is None
        self.read_accessor = weakref.ref(read_accessor)
        self.target = weakref.ref(target)
        self.pinname = pinname
        self.path = path

from ...core.cell import celltypes, subcelltypes
from .expression import Expression