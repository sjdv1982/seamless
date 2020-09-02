import weakref
from ..cache.buffer_cache import buffer_cache
from .. import destroyer

import json
import asyncio

import logging
logger = logging.getLogger("seamless")

def print_info(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)

def print_warning(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)

def print_debug(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)

def print_error(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)

RECOMPUTE_OVER_REMOTE = 1000000 # after this threshold, better to recompute than to download remotelt
                                # TODO: have some dynamic component based on:
                                # - stored recomputation time from provenance server
                                # - internet connection speed

class CacheManager:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.checksum_refs = {}

        self.cell_to_ref = {}
        self.inactive_expressions = set()
        self.expression_to_ref = {}
        self.expression_to_result_checksum = {}
        self.transformer_to_result_checksum = {}
        self.reactor_to_refs = {}
        self.inchannel_to_ref = {}
        self.macro_exceptions = {}
        self.reactor_exceptions = {}

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
        # Special case, since we never actually clear expression caches,
        #  we just inactivate them if not referenced
        if expression in self.inactive_expressions:
            checksum = self.expression_to_ref.get(expression)
            if checksum is not None:
                self.incref_checksum(
                    checksum,
                    expression,
                    False,
                    False
                )
            checksum = self.expression_to_result_checksum.get(expression)
            if checksum is not None:
                self.incref_checksum(
                    checksum,
                    expression,
                    False,
                    True
                )
            self.inactive_expressions.remove(expression)
            return True
        else:
            assert expression not in self.expression_to_ref
            self.expression_to_ref[expression] = None
            assert expression not in self.expression_to_result_checksum
            self.expression_to_result_checksum[expression] = None
            return False

    def register_transformer(self, transformer):
        assert transformer not in self.transformer_to_result_checksum
        self.transformer_to_result_checksum[transformer] = None
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

    def incref_checksum(self, checksum, refholder, authoritative, result):
        if checksum is None:
            return
        #print("INCREF CHECKSUM", checksum.hex(), refholder, result)
        incref_hash_pattern = False
        if isinstance(refholder, Cell):
            assert not result
            assert self.cell_to_ref[refholder] is None
            self.cell_to_ref[refholder] = (checksum, authoritative)
            cell = refholder
            if cell._hash_pattern is not None:
                incref_hash_pattern = True
        elif isinstance(refholder, Expression):
            #print("INCREF EXPRESSION", refholder._get_hash(), result)
            assert not authoritative
            if refholder not in self.inactive_expressions:
                if not result:
                    v = self.expression_to_ref[refholder]
                    assert v is None or v == checksum, refholder
                    self.expression_to_ref[refholder] = checksum
                else:
                    assert checksum != refholder.checksum
                    v = self.expression_to_result_checksum[refholder]
                    assert v is None or v == checksum, refholder
                    self.expression_to_result_checksum[refholder] = checksum
        elif isinstance(refholder, Transformer):
            assert not authoritative
            assert result
            assert self.transformer_to_result_checksum[refholder] is None
            self.transformer_to_result_checksum[refholder] = checksum
        elif isinstance(refholder, Inchannel):
            assert not authoritative
            assert not result
            assert self.inchannel_to_ref[refholder] is None
            self.inchannel_to_ref[refholder] = checksum
        elif isinstance(refholder, Library):
            pass
        else:
            raise TypeError(type(refholder))

        refh = refholder
        if checksum not in self.checksum_refs:
            self.checksum_refs[checksum] = []
            try:
                buffer_cache.incref(checksum, authoritative)
            finally:
                self.checksum_refs[checksum].append((refh, result))
        else:
            self.checksum_refs[checksum].append((refh, result))
        #print("cachemanager INCREF", checksum.hex(), len(self.checksum_refs[checksum]))
        if incref_hash_pattern:
            deep_buffer = buffer_cache.get_buffer(checksum)
            deep_structure = deserialize(deep_buffer, checksum, "mixed", False)
            sub_checksums = deep_structure_to_checksums(
                deep_structure, cell._hash_pattern
            )
            for sub_checksum in sub_checksums:
                #print("INCREF SUB-CHECKSUM", sub_checksum, cell)
                buffer_cache.incref(bytes.fromhex(sub_checksum), authoritative)


    async def fingertip(self, checksum, *, must_have_cell=False):
        """Tries to put the checksum's corresponding buffer 'at your fingertips'
        Normally, first reverse provenance (recompute) is tried,
         then remote download.
        If the checksum is held by any cell with restricted fingertip parameters,
         one or both strategies may be skipped, or they are reversed

        If must_have_cell is True, then there must be a cell that holds the checksum,
         else no fingertip strategy is performed; this is a security feature used by
         the shareserver, which makes it safe to re-compute a checksum-to-buffer
         request dynamically, without allowing arbitrary computation
        """

        from ..cache import CacheMissError
        from ..cache.transformation_cache import calculate_checksum
        from .tasks.evaluate_expression import EvaluateExpressionTask
        if checksum is None:
            return
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        assert isinstance(checksum, bytes), checksum
        buffer = buffer_cache.get_buffer(checksum)
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
                celltype, subcelltype, sem_checksum = transformation[pinname]
                sem2syn = tf_cache.semantic_to_syntactic_checksums
                semkey = (sem_checksum, celltype, subcelltype)
                checksum2 = sem2syn.get(semkey, [sem_checksum])[0]
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
        for refholder, result in self.checksum_refs.get(checksum, []):
            if isinstance(refholder, Cell):
                cell = refholder
                has_cell = True
                c_remote = rmap[cell._fingertip_remote]
                remote = min(remote, c_remote)
                c_recompute = rmap[cell._fingertip_recompute]
                recompute = min(recompute, c_recompute)

        if must_have_cell and not has_cell:
            raise CacheMissError(checksum.hex())

        if recompute - remote in (0, 1) and remote > 0:
            buffer_length = buffer_cache.get_buffer_length(checksum)
            if buffer_length is None:
                buffer_length = await get_buffer_length_remote(
                    checksum,
                    remote_peer_id=None
                )
            if buffer_length is not None:
                if buffer_length <= RECOMPUTE_OVER_REMOTE:
                    remote = recompute + 1

        if remote > recompute:
            try:
                buffer = await get_buffer_remote(
                    checksum,
                    None
                )
                if buffer is not None:
                    return buffer
            except CacheMissError:
                pass

        for refholder, result in self.checksum_refs.get(checksum, []):
            if not result:
                continue
            if isinstance(refholder, Expression):
                coros.append(fingertip_expression(refholder))
            elif isinstance(refholder, Transformer) and recompute:
                tf_checksum = tf_cache.transformer_to_transformations[refholder]
                transformation = tf_cache.transformations[tf_checksum]
                coros.append(fingertip_transformation(transformation, tf_checksum))

        tasks = [asyncio.ensure_future(c) for c in coros]
        while len(tasks):
            _, tasks  = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            buffer = buffer_cache.get_buffer(checksum)
            if buffer is not None:
                for task in tasks:
                    task.cancel()
                return buffer

        buffer = buffer_cache.get_buffer(checksum)
        if buffer is not None:
            return buffer

        if remote > 0 and remote <= recompute:
            try:
                buffer = await get_buffer_remote(
                    checksum,
                    None
                )
                if buffer is not None:
                    return buffer
            except CacheMissError:
                pass

        raise CacheMissError(checksum.hex())


    def decref_checksum(self, checksum, refholder, authoritative, result, *, destroying=False):
        if checksum not in self.checksum_refs:
            if checksum is None:
                cs = "<None>"
            else:
                cs = checksum.hex()
            print_warning("cachemanager: cannot decref unknown checksum {}".format(cs))
            return
        if isinstance(refholder, Cell):
            assert self.cell_to_ref[refholder] is not None, refholder
            self.cell_to_ref[refholder] = None
            cell = refholder
            if not destroying and cell._hash_pattern is not None:
                deep_buffer = buffer_cache.get_buffer(checksum)
                deep_structure = deserialize(deep_buffer, checksum, "mixed", False)
                sub_checksums = deep_structure_to_checksums(
                    deep_structure, cell._hash_pattern
                )
                for sub_checksum in sub_checksums:
                    buffer_cache.decref(bytes.fromhex(sub_checksum))

        elif isinstance(refholder, Expression):
            # Special case, since we never actually clear expression caches,
            #  we just inactivate them if not referenced
            #print("DECREF EXPRESSION", refholder._get_hash(), result)
            if result:
                assert self.expression_to_result_checksum[refholder] is not None
            else:
                assert self.expression_to_ref[refholder] is not None
        elif isinstance(refholder, Transformer):
            assert self.transformer_to_result_checksum[refholder] is not None
            self.transformer_to_result_checksum[refholder] = None
        elif isinstance(refholder, Inchannel):
            assert self.inchannel_to_ref[refholder] is not None
            self.inchannel_to_ref[refholder] = None
        elif isinstance(refholder, Library):
            pass
        else:
            raise TypeError(type(refholder))
        try:
            refh = refholder
            self.checksum_refs[checksum].remove((refh, result))
        except ValueError:
            print_warning("""cachemanager: cannot remove unknown checksum ref:
checksum: {}
refholder: {}
is authoritative: {}
is result: {}
""".format(checksum.hex(), refholder, authoritative, result))
            return
        #print("cachemanager DECREF", checksum.hex(), len(self.checksum_refs[checksum]))
        if len(self.checksum_refs[checksum]) == 0:
            buffer_cache.decref(checksum)
            self.checksum_refs.pop(checksum)

    @destroyer
    def destroy_cell(self, cell):
        ref = self.cell_to_ref[cell]
        if ref is not None:
            checksum, authoritative = ref
            if checksum is not None and cell._hash_pattern is not None:
                buffer = buffer_cache.get_buffer(checksum)
                if buffer is not None:
                    deep_structure = json.loads(buffer) # non-standard, but we could be in precarious territory
                    sub_checksums = deep_structure_to_checksums(deep_structure, cell._hash_pattern)
                    for sub_checksum in sub_checksums:
                        buffer_cache.decref(bytes.fromhex(sub_checksum))
            self.decref_checksum(checksum, cell, authoritative, False, destroying=True)
        self.cell_to_ref.pop(cell)

    @destroyer
    def destroy_structured_cell(self, sc):
        for inchannel in sc.inchannels.values():
            ref = self.inchannel_to_ref[inchannel]
            if ref is not None:
                checksum = ref
                self.decref_checksum(checksum, inchannel, False, False)
            self.inchannel_to_ref.pop(inchannel)

    @destroyer
    def destroy_transformer(self, transformer):
        ref = self.transformer_to_result_checksum[transformer]
        if ref is not None:
            checksum = ref
            self.decref_checksum(checksum, transformer, False, True)
        self.transformer_to_result_checksum.pop(transformer)
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
                self.decref_checksum(checksum, reactor, False, False)
        self.reactor_exceptions.pop(reactor)

    @destroyer
    def destroy_expression(self, expression):
        # Special case, since we never actually clear expression caches,
        #  we just inactivate them if not referenced
        assert expression not in self.inactive_expressions
        ref = self.expression_to_ref[expression]
        if ref is not None:
            checksum = ref
            self.decref_checksum(checksum, expression, False, False)
        ref = self.expression_to_result_checksum[expression]
        if ref is not None:
            checksum = ref
            self.decref_checksum(checksum, expression, False, True)
        self.inactive_expressions.add(expression)

    def check_destroyed(self):
        attribs = (
            "checksum_refs",
            "cell_to_ref",
            "expression_to_ref",
            "expression_to_result_checksum",
            "transformer_to_result_checksum",
            "reactor_to_refs"
        )
        name = self.__class__.__name__
        for attrib in attribs:
            a = getattr(self, attrib)
            if attrib == "checksum_refs":
                a = [aa for aa in a.values() if aa != []]
            elif attrib.startswith("expression_to"):
                a = [aa for aa in a if aa not in self.inactive_expressions]
            if len(a):
                print_warning(name + ", " + attrib + ": %d undestroyed"  % len(a))

from ..cell import Cell
from ..transformer import Transformer
from ..structured_cell import Inchannel
from ..reactor import Reactor
from .expression import Expression
from ..protocol.deep_structure import deep_structure_to_checksums
from ..protocol.deserialize import deserialize_sync as deserialize
from ..protocol.get_buffer import (
    get_buffer_remote, get_buffer_length_remote, CacheMissError
)