import weakref
from ..cache.buffer_cache import buffer_cache

class CacheManager:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.checksum_refs = {}
        self.buffer_cache = buffer_cache
        self.cell_to_ref = {}
        self.expression_to_ref = {}
        self.transformer_to_ref = {}
        self.reactor_to_refs = {}  
        self.macro_exceptions = {}
        self.reactor_exceptions = {}

        # Quick local expression cache
        # Hang onto this indefinitely
        # No expression cache at the level of communionserver or redis
        #  (if expressions are really long to evaluate, use deepcells)
        self.expression_to_checksum = {} 
        
        # for now, just a single global transformation cache
        from ..cache.transformation_cache import transformation_cache
        self.transformation_cache = transformation_cache
        
    def register_cell(self, cell):
        assert cell not in self.cell_to_ref
        self.cell_to_ref[cell] = None

    def register_expression(self, expression):
        expression = expression
        assert expression not in self.expression_to_ref
        self.expression_to_ref[expression] = None

    def register_transformer(self, transformer):
        assert transformer not in self.transformer_to_ref
        self.transformer_to_ref[transformer] = None
        self.transformation_cache.register_transformer(transformer)

    def register_macro(self, macro):
        assert macro not in self.macro_exceptions
        self.macro_exceptions[macro] = None

    def register_reactor(self, reactor):
        assert reactor not in self.reactor_to_ref
        raise NotImplementedError # livegraph branch
        # TODO: store a dictionary of outputpin/editpin-to-ref 
        self.reactor_exceptions[reactor] = None

    def incref_checksum(self, checksum, refholder, authority):
        if checksum is None:
            return
        if checksum not in self.checksum_refs:
            self.buffer_cache.incref(checksum)
            self.checksum_refs[checksum] = []
        if isinstance(refholder, Cell):
            assert self.cell_to_ref[refholder] is None
            self.cell_to_ref[refholder] = (checksum, authority) 
        elif isinstance(refholder, Expression):
            assert self.expression_to_ref[refholder] is None
            self.expression_to_ref[refholder] = (checksum, authority) 
        elif isinstance(refholder, Transformer):
            assert not authority
            assert self.transformer_to_ref[refholder] is None
            self.transformer_to_ref[refholder] = checksum
        elif isinstance(refholder, Reactor):
            assert self.reactor_to_ref[refholder] is None
            raise NotImplementedError # livegraph branch
        else:
            raise TypeError(refholder)
        self.checksum_refs[checksum].append((refholder, authority))
        #print("INCREF", checksum.hex(), self.checksum_refs[checksum])

    def decref_checksum(self, checksum, refholder, authority):        
        if isinstance(refholder, Cell):
            assert self.cell_to_ref[refholder] is not None
            self.cell_to_ref[refholder] = None
        elif isinstance(refholder, Expression):
            assert self.expression_to_ref[refholder] is not None
            self.expression_to_ref.pop(refholder)
        elif isinstance(refholder, Transformer):
            assert self.transformer_to_ref[refholder] is not None
            self.transformer_to_ref[refholder] = None
        elif isinstance(refholder, Reactor):
            assert self.reactor_to_ref[refholder] is not None
            raise NotImplementedError # livegraph branch
        else:
            raise TypeError(refholder)
        self.checksum_refs[checksum].remove((refholder, authority))
        #print("DECREF", checksum.hex(), self.checksum_refs[checksum])
        if len(self.checksum_refs) == 0:
            self.buffer_cache.decref(checksum)
            self.checksum_refs.pop(checksum)        

    def destroy_cell(self, cell):
        ref = self.cell_to_ref[cell]
        if ref is not None:
            checksum, authority = ref
            self.decref_checksum(checksum, cell, authority)
        self.cell_to_ref.pop(cell)

    def destroy_transformer(self, transformer):
        ref = self.transformer_to_ref[transformer]
        if ref is not None:
            checksum = ref
            self.decref_checksum(checksum, transformer, False)
        self.transformer_to_ref.pop(transformer)
        self.transformation_cache.destroy_transformer(transformer)

    def destroy_macro(self, macro):
        self.macro_exceptions.pop(macro)

    def destroy_reactor(self, reactor):
        raise NotImplementedError # livegraph branch
        self.reactor_exceptions.pop(reactor)

    def check_destroyed(self):        
        attribs = (
            "checksum_refs", 
            "cell_to_ref", 
            "expression_to_ref",
            "transformer_to_ref",
            "reactor_to_refs"
        )
        name = self.__class__.__name__        
        for attrib in attribs:
            a = getattr(self, attrib)
            if attrib == "checksum_refs":
                a = [aa for aa in a.values() if aa != []]
            if len(a):                
                print(name + ", " + attrib + ": %d undestroyed"  % len(a))

from ..cell import Cell
from ..transformer import Transformer
from ..reactor import Reactor
from .expression import Expression