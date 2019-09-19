import weakref
from ..cache.buffer_cache import buffer_cache
from .. import destroyer

import sys
import json

def log(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)

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
        # No expression cache at the level of communion_server or redis
        #  (if expressions are really long to evaluate, use deepcells)
        self.expression_to_checksum = {} 
        
        # for now, just a single global transformation cache
        from ..cache.transformation_cache import transformation_cache
        self.transformation_cache = transformation_cache

        self._destroying = set()
        
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
        assert reactor not in self.reactor_to_refs
        refs = {}
        for pinname in reactor.outputs:
            refs[pinname] = None
        self.reactor_to_refs[reactor] = refs
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
        elif isinstance(refholder, Library):
            pass
        else:
            raise TypeError(type(refholder))
        self.checksum_refs[checksum].append((refholder, authority))
        #print(self, "INCREF", checksum.hex(), self.checksum_refs[checksum])

    def decref_checksum(self, checksum, refholder, authority):
        if checksum is None:
            if isinstance(refholder, Expression):
                if refholder in self.expression_to_ref:
                    assert self.expression_to_ref[refholder] is None
                    self.expression_to_ref.pop(refholder)
            return
        if isinstance(refholder, Cell):
            assert self.cell_to_ref[refholder] is not None
            self.cell_to_ref[refholder] = None
        elif isinstance(refholder, Expression):
            assert self.expression_to_ref[refholder] is not None
            self.expression_to_ref.pop(refholder)
        elif isinstance(refholder, Transformer):
            assert self.transformer_to_ref[refholder] is not None
            self.transformer_to_ref[refholder] = None
        elif isinstance(refholder, Library):
            pass
        else:
            raise TypeError(type(refholder))
        #print("cachemanager DECREF", checksum.hex())
        self.checksum_refs[checksum].remove((refholder, authority))        
        if len(self.checksum_refs[checksum]) == 0:            
            self.buffer_cache.decref(checksum)
            self.checksum_refs.pop(checksum)        

    @destroyer
    def destroy_cell(self, cell):
        ref = self.cell_to_ref[cell]
        if ref is not None:
            checksum, authority = ref
            if checksum is not None and cell._hash_pattern is not None:
                buffer = self.buffer_cache.get_buffer(checksum)
                if buffer is not None:
                    deep_structure = json.loads(buffer) # non-standard, but we could be in precarious territory
                    sub_checksums = deep_structure_to_checksums(deep_structure, cell._hash_pattern)
                    for sub_checksum in sub_checksums:
                        self.buffer_cache.decref(bytes.fromhex(sub_checksum))
            self.decref_checksum(checksum, cell, authority)
        self.cell_to_ref.pop(cell)

    @destroyer
    def destroy_transformer(self, transformer):
        ref = self.transformer_to_ref[transformer]
        if ref is not None:
            checksum = ref
            self.decref_checksum(checksum, transformer, False)
        self.transformer_to_ref.pop(transformer)
        self.transformation_cache.destroy_transformer(transformer)

    @destroyer
    def destroy_macro(self, macro):
        self.macro_exceptions.pop(macro)

    @destroyer
    def destroy_reactor(self, reactor):
        refs = self.reactor_to_refs.pop(reactor)
        for pinname in reactor.outputs:
            ref = refs[pinname]
            if ref is not None:
                checksum = ref
                self.decref_checksum(checksum, reactor, False)
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
                log(name + ", " + attrib + ": %d undestroyed"  % len(a))

from ..cell import Cell
from ..transformer import Transformer
from ..reactor import Reactor
from ..library import Library
from .expression import Expression
from ..protocol.deep_structure import deep_structure_to_checksums