import weakref

class CacheManager:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.cell_to_checksum = {}
        #self.value_cache = ValueCache() #TODO: livegraph branch
    
    def register_cell(self, cell):
        assert cell not in self.cell_to_checksum
        self.cell_to_checksum[cell] = None

    def change_cell_checksum(self, cell, checksum):
        old_checksum = self.cell_to_checksum[cell]
        if old_checksum is not None:
            self.value_cache.decref(old_checksum)
        if checksum is not None:
            self.value_cache.incref(checksum)
        self.cell_to_checksum[cell] = checksum
    
    def destroy_cell(self, cell):
        self.change_cell_checksum(cell, None)
        self.cell_to_checksum.pop(cell)