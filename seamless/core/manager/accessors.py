import weakref

class Accessor:
    pass

class ReadAccessor(Accessor):
    def __init__(self, manager, path, celltype, subcelltype=None):
        self.manager = weakref.ref(manager)
        self.path = path
        self.celltype = celltype    
        self.subcelltype = subcelltype


class WriteAccessor(Accessor):
    def __init__(self, manager, path, celltype):
        self.manager = weakref.ref(manager)
        self.path = path
        self.celltype = celltype    

from ...core.cell import celltypes #[cellclass._celltype for every cellclass], subcelltypes