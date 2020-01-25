import weakref
from ..cache.buffer_cache import buffer_cache
from .. import destroyer

import sys
import json
import asyncio

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
        self.inchannel_to_ref = {}
        self.macro_exceptions = {}
        self.reactor_exceptions = {}

        # Quick local expression cache
        # Hang onto this indefinitely
        # No expression cache at the level of communion_server or redis
        #  (if expressions are really long to compute, use deepcells)
        self.expression_to_checksum = {} 
        
        # for now, just a single global transformation cache
        from ..cache.transformation_cache import transformation_cache
        self.transformation_cache = transformation_cache

        self._destroying = set()
        
    def register_cell(self, cell):
        assert cell not in self.cell_to_ref
        self.cell_to_ref[cell] = None

    def register_structured_cell(self, sc):
        for inchannel in sc.inchannels.values():
            self.inchannel_to_ref[inchannel] = None

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
        #print("INCREF CHECKSUM", checksum, refholder)
        if checksum not in self.checksum_refs:
            self.buffer_cache.incref(checksum)
            self.checksum_refs[checksum] = []
        if isinstance(refholder, Cell):
            assert self.cell_to_ref[refholder] is None
            self.cell_to_ref[refholder] = (checksum, authority) 
            cell = refholder
            if cell._hash_pattern is not None:
                deep_buffer = self.buffer_cache.get_buffer(checksum)
                deep_structure = deserialize(deep_buffer, checksum, "mixed", False)
                sub_checksums = deep_structure_to_checksums(
                    deep_structure, cell._hash_pattern
                )
                for sub_checksum in sub_checksums:
                    #print("INCREF SUB-CHECKSUM", sub_checksum, cell)
                    self.buffer_cache.incref(bytes.fromhex(sub_checksum))
        elif isinstance(refholder, Expression):
            assert self.expression_to_ref[refholder] is None
            self.expression_to_ref[refholder] = (checksum, authority) 
        elif isinstance(refholder, Transformer):
            assert not authority
            assert self.transformer_to_ref[refholder] is None
            self.transformer_to_ref[refholder] = checksum
        elif isinstance(refholder, Inchannel):
            assert not authority
            assert self.inchannel_to_ref[refholder] is None
            self.inchannel_to_ref[refholder] = checksum
        elif isinstance(refholder, Library):
            pass
        else:
            raise TypeError(type(refholder))
        self.checksum_refs[checksum].append((refholder, authority))
        #print(self, "INCREF", checksum.hex(), self.checksum_refs[checksum])

    async def fingertip(self, checksum, *, must_have_cell=False):
        """Tries to put the checksum's corresponding buffer 'at your fingertips'
        Normally, first reverse provenance (recompute) is tried,
         then remote download.
        If the checksum is held by any cell with restricted fingertip parameters,
         one or both strategies may be skipped, or they are reversed

        If must_have_cell is True, then there must be a cell that holds the checksum,
         else no fingertip strategy is performed
        """

        from ..cache import CacheMissError
        from ..cache.transformation_cache import calculate_checksum
        from .tasks.evaluate_expression import EvaluateExpressionTask        
        if checksum is None:
            return
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        assert isinstance(checksum, bytes), checksum
        buffer = self.buffer_cache.get_buffer(checksum)
        if buffer is not None:
            return buffer

        coros = []
        manager = self.manager()
        tf_cache = self.transformation_cache
        
        async def fingertip_transformation(transformation, tf_checksum):            
            coros = []
            for pinname in transformation:
                if pinname.startswith("__"):
                    continue
                sem_checksum = transformation[pinname][2]
                sem2syn = tf_cache.semantic_to_syntactic_checksums
                checksum2 = sem2syn.get(sem_checksum, [sem_checksum])[0]
                coros.append(self.fingertip(checksum2))
            await asyncio.gather(*coros)
            job = tf_cache.run_job(transformation, tf_checksum)
            if job is not None:                
                await asyncio.shield(job.future)

        async def fingertip_expression(expression):
            await self.fingertip(expression.checksum)
            task = EvaluateExpressionTask(
                manager, expression, fingertip_mode=True
            )
            await task.run()

        rmap = {True: 2, None: 1, False: 0}
        remote, recompute= 2, 2 # True, True
        has_cell = False
        for refholder, auth in self.checksum_refs.get(checksum, []):
            if isinstance(refholder, Cell):
                cell = refholder
                has_cell = True
                c_remote = rmap[cell._fingertip_remote]
                remote = min(remote, c_remote)
                c_recompute = rmap[cell._fingertip_recompute]
                recompute = min(recompute, c_recompute)

        if must_have_cell and not has_cell:
            raise CacheMissError(checksum.hex())

        if remote > recompute:
            try:
                buffer = await get_buffer_remote(checksum, None)
                if buffer is not None:
                    return buffer
            except CacheMissError:
                pass
        
        for refholder, auth in self.checksum_refs.get(checksum, []):
            if isinstance(refholder, Expression):
                if refholder.checksum != checksum:
                    if self.expression_to_checksum[refholder] == checksum:                    
                        coros.append(fingertip_expression(refholder))
            elif isinstance(refholder, Transformer) and recompute:
                tf_checksum = tf_cache.transformer_to_transformations[refholder]
                transformation = tf_cache.transformations[tf_checksum]
                cs = tf_cache.transformation_results.get(tf_checksum, (None, None))[0]
                if cs == checksum:
                    coros.append(fingertip_transformation(transformation, tf_checksum))
            
        tasks = [asyncio.ensure_future(c) for c in coros]
        while len(tasks):
            _, tasks  = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            buffer = self.buffer_cache.get_buffer(checksum)
            if buffer is not None:
                for task in tasks:
                    task.cancel()
                return buffer       

        if remote > 0 and remote <= recompute:
            try:
                buffer = await get_buffer_remote(checksum, None)
                if buffer is not None:
                    return buffer
            except CacheMissError:
                pass

        raise CacheMissError(checksum.hex())
        

    def decref_checksum(self, checksum, refholder, authority, *, destroying=False):
        if checksum is None:
            if isinstance(refholder, Expression):
                if refholder in self.expression_to_ref:
                    assert self.expression_to_ref[refholder] is None
                    self.expression_to_ref.pop(refholder)
            return
        if isinstance(refholder, Cell):
            assert self.cell_to_ref[refholder] is not None
            self.cell_to_ref[refholder] = None
            cell = refholder
            if not destroying and cell._hash_pattern is not None:
                deep_buffer = self.buffer_cache.get_buffer(checksum)
                deep_structure = deserialize(deep_buffer, checksum, "mixed", False)
                sub_checksums = deep_structure_to_checksums(
                    deep_structure, cell._hash_pattern
                )
                for sub_checksum in sub_checksums:
                    self.buffer_cache.decref(bytes.fromhex(sub_checksum))

        elif isinstance(refholder, Expression):
            assert self.expression_to_ref[refholder] is not None
            self.expression_to_ref.pop(refholder)
        elif isinstance(refholder, Transformer):
            assert self.transformer_to_ref[refholder] is not None
            self.transformer_to_ref[refholder] = None
        elif isinstance(refholder, Inchannel):
            assert self.inchannel_to_ref[refholder] is not None
            self.inchannel_to_ref[refholder] = None
        elif isinstance(refholder, Library):
            pass
        else:
            raise TypeError(type(refholder))
        #print("cachemanager DECREF", checksum.hex())
        try:
            self.checksum_refs[checksum].remove((refholder, authority))        
        except ValueError:
            self.checksum_refs[checksum][:] = \
              [l for l in self.checksum_refs[checksum] if l[0] is not refholder]
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
            self.decref_checksum(checksum, cell, authority, destroying=True)
        self.cell_to_ref.pop(cell)

    @destroyer
    def destroy_structured_cell(self, sc):
        for inchannel in sc.inchannels.values():
            ref = self.inchannel_to_ref[inchannel]
            if ref is not None:
                checksum = ref
                self.decref_checksum(checksum, inchannel, False)
            self.inchannel_to_ref.pop(inchannel)

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
from ..structured_cell import Inchannel
from ..reactor import Reactor
from .expression import Expression
from ..protocol.deep_structure import deep_structure_to_checksums
from ..protocol.deserialize import deserialize_sync as deserialize
from ..protocol.get_buffer import get_buffer_remote, CacheMissError