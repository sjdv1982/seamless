import weakref
from weakref import WeakValueDictionary

class CellCache:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.cell_to_accessors = {} #cell => list-of-accessors (output)        
        self.cell_to_authority = {} # cell => True, False or "partial"
        self.cell_to_buffer_checksums = {} # buffer checksums of the cell as a whole

        # TODO: links to annotation caches; reverse caches
        # reverse cache:
        # self.cell_from_accessor = {} # cellid => input accessor