import weakref
from ..cache.value_cache import value_cache

class CacheManager:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.checksum_refs = {}
        self.value_cache = value_cache
        self.cell_to_ref = {}
        self.expression_to_ref = {}

    def register_cell(self, cell):
        self.cell_to_ref[cell] = None

    def register_expression(self, expression):
        self.expression_to_ref[expression] = None

    def incref_checksum(self, checksum, refholder, authority):
        if checksum is None:
            return
        if checksum not in self.checksum_refs:
            self.value_cache.incref(checksum)
            self.checksum_refs[checksum] = []
        if isinstance(refholder, Cell):
            assert self.cell_to_ref[refholder] is None
            self.cell_to_ref[refholder] = (checksum, authority) 
        elif isinstance(refholder, Expression):
            assert refholder not in self.expression_to_ref
            self.expression_to_ref[refholder] = (checksum, authority) 
        else:
            raise TypeError(refholder)
        self.checksum_refs[checksum].append((refholder, authority))
        #print("INCREF", checksum.hex(), self.checksum_refs[checksum])

    def decref_checksum(self, checksum, refholder, authority):        
        if isinstance(refholder, Cell):
            assert self.cell_to_ref[refholder] is not None
            self.cell_to_ref[refholder] = None
        elif isinstance(refholder, Expression):
            self.expression_to_ref.pop(refholder)
        else:
            raise TypeError(refholder)
        self.checksum_refs[checksum].remove((refholder, authority))
        #print("DECREF", checksum.hex(), self.checksum_refs[checksum])
        if len(self.checksum_refs) == 0:
            self.value_cache.decref(checksum)
            self.checksum_refs.pop(checksum)        

    def destroy_cell(self, cell):
        ref = self.cell_to_ref[cell]
        if ref is not None:
            checksum, authority = ref
            self.decref_checksum(checksum, cell, authority)
        self.cell_to_ref.pop(cell)

    def check_destroyed(self):        
        attribs = ("checksum_refs", "cell_to_ref", "expression_to_ref")
        name = self.__class__.__name__        
        for attrib in attribs:
            a = getattr(self, attrib)
            if attrib == "checksum_refs":
                a = [aa for aa in a.values() if aa != []]
            if len(a):                
                print(name + ", " + attrib + ": %d undestroyed"  % len(a))

from ..cell import Cell
from .expression import Expression