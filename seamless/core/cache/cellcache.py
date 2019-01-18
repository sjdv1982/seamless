import weakref
from weakref import WeakValueDictionary

class CellCache:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.cells = WeakValueDictionary() #cellid => cell
        self.cell_to_accessors = {} #cellid => list-of-accessors (output)        
        self.cell_to_authority = {} # cellid => True, False or "partial"

        # TODO: links to annotation caches; reverse caches
        # reverse cache:
        # self.cell_from_accessor = {} # cellid => input accessor