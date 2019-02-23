import weakref
from weakref import WeakValueDictionary

class CellCache:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.cell_to_accessors = {} #cell => dict-of-subpath => list-of-accessors (output)        
        self.cell_to_authority = {} # cell => dict-of-subpath => True, False or "partial"
        self.cell_to_buffer_checksums = {} # buffer checksums of cells as a whole
        self.cell_from_upstream = {} # cell => dict-of-subpath => X, where X is 1. or 2. 
                                     # 1. a single outputpin or accessor
                                     # 2. a list of editpins

        # TODO: links to annotation caches; reverse caches
        # reverse cache:
        