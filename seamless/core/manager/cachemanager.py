import traceback
import weakref
import copy
import json
import asyncio

import logging

from ...download_buffer import download_buffer_from_servers
from ..cache.buffer_cache import buffer_cache
from ... import calculate_dict_checksum


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

RECOMPUTE_OVER_REMOTE = int(100e6) # after this threshold, better to recompute than to download remotely
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
        self.join_cache = {}
        self.rev_join_cache = {}
        
        # for now, just a single global transformation cache
        from ..cache.transformation_cache import transformation_cache
        self.transformation_cache = transformation_cache

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
            self.inactive_expressions.remove(expression)
            checksum = self.expression_to_ref.get(expression)
            if checksum is not None:
                self.incref_checksum(
                    checksum,
                    expression,
                    authoritative=False,
                    result=False
                )
            checksum = self.expression_to_result_checksum.get(expression)
            if checksum is not None and checksum != expression.checksum:
                self.incref_checksum(
                    checksum,
                    expression,
                    authoritative=False,
                    result=True
                )
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
        for pinname in reactor._pins:
            if reactor._pins[pinname].io == "output":
                refs[pinname] = None
        self.reactor_to_refs[reactor] = refs
        self.reactor_exceptions[reactor] = None

    def incref_checksum(self, checksum, refholder, authoritative, result):
        """
        NOTE: incref/decref must happen within one async step
        Therefore, the direct or indirect call of _sync versions of coroutines
        (e.g. deserialize_sync, which launches coroutines and waits for them)
        IS NOT ALLOWED
        """
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
            #print("INCREF EXPRESSION", refholder, result)
            assert not authoritative
            assert refholder not in self.inactive_expressions
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
        #elif isinstance(refholder, Library): # yagni??
        #    pass
        else:
            raise TypeError(type(refholder))

        refh = refholder
        if checksum not in self.checksum_refs:
            self.checksum_refs[checksum] = set()
            try:
                buffer_cache.incref(checksum, authoritative)
            finally:
                item = (refh, result)
                self.checksum_refs[checksum].add(item)
        else:
            item = (refh, result)
            self.checksum_refs[checksum].add(item)
        #print("cachemanager INCREF", checksum.hex(), len(self.checksum_refs[checksum]))
        if incref_hash_pattern:
            cell = refholder
            deeprefmanager.incref_deep_buffer(checksum, cell._hash_pattern, authoritative, cell=cell)
    
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
        return await self._fingertip(checksum, must_have_cell=must_have_cell, done=set())

    async def _fingertip(self, checksum, *, must_have_cell, done):
        from ..cache import CacheMissError
        from .tasks.evaluate_expression import evaluate_expression
        from .tasks.deserialize_buffer import DeserializeBufferTask
        from .tasks.serialize_buffer import SerializeToBufferTask
        from seamless.highlevel.direct.run import run_transformation_dict
        from seamless.config import database
        from seamless.util import is_forked
        from seamless.highlevel.direct.run import TRANSFORMATION_STACK

        if checksum is None:
            return
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        assert isinstance(checksum, bytes), checksum
        buffer = get_buffer(checksum, remote=True)
        if buffer is not None:
            return buffer
        if checksum in done:
            return

        done.add(checksum)
        coros = []
        manager = self.manager()
        tf_cache = self.transformation_cache

        async def fingertip_transformation(transformation, tf_checksum):
            coros = []
            for pinname in transformation:
                if pinname == "__env__":
                    cs = bytes.fromhex(transformation[pinname])
                    coros.append(self._fingertip(cs, must_have_cell=False, done=done))
                    continue
                if pinname.startswith("__"):
                    continue
                celltype, subcelltype, sem_checksum0 = transformation[pinname]
                sem_checksum = bytes.fromhex(sem_checksum0) if sem_checksum0 is not None else None
                sem2syn = tf_cache.semantic_to_syntactic_checksums
                semkey = (sem_checksum, celltype, subcelltype)
                checksum2 = sem2syn.get(semkey, [sem_checksum])[0]
                coros.append(self._fingertip(checksum2, must_have_cell=False, done=done))
            await asyncio.gather(*coros)
            
            if is_forked():                
                run_transformation_dict(transformation, fingertip=True)
            else:
                job = tf_cache.run_job(transformation, tf_checksum, fingertip=True)
                if job is not None:
                    await asyncio.shield(job.future)

        async def fingertip_expression(expression):
            await self._fingertip(expression.checksum, must_have_cell=False, done=done)
            await evaluate_expression(
                expression, manager=manager, fingertip_mode=True
            )

        async def fingertip_join(checksum, join_dict):
            hash_pattern = join_dict.get("hash_pattern")
            inchannels0 = join_dict["inchannels"]
            inchannels = {}
            for path0, cs in inchannels0.items():
                path = json.loads(path0)
                if isinstance(path, list):
                    path = tuple(path)
                inchannels[path] = cs
            paths = sorted(list(inchannels.keys()))
            if "auth" in join_dict:
                auth_checksum = bytes.fromhex(join_dict["auth"])
                auth_buffer = await self._fingertip(auth_checksum, must_have_cell=False, done=done)
                value = await DeserializeBufferTask(
                    manager, auth_buffer, auth_checksum, "mixed", copy=True
                ).run()
            else:
                if isinstance(paths[0], int):
                    value = []
                elif isinstance(paths[0], (list, tuple)) and len(paths[0]) and isinstance(paths[0][0], int):
                    value = []
                else:
                    value = None
                    if hash_pattern is not None:
                        if isinstance(hash_pattern, dict):
                            for k in hash_pattern:
                                if k.startswith("!"):
                                    value = []
                                    break
                    if value is None:
                        value = {}
            for path in paths:
                subchecksum = bytes.fromhex(inchannels[path])
                sub_buffer = None
                if hash_pattern is None or access_hash_pattern(hash_pattern, path) not in ("#", '##'):
                    sub_buffer = await self._fingertip(subchecksum, must_have_cell=False, done=done)
                await set_subpath_checksum(value, hash_pattern, path, subchecksum, sub_buffer)
            buf = await SerializeToBufferTask(
                manager, value, "mixed",
                use_cache=True
            ).run()
            buffer_cache.cache_buffer(checksum, buf)
            return

        rmap = {True: 2, None: 1, False: 0}
        remote, recompute= 2, 2 # True, True
        is_deep = False
        has_cell = False
        for refholder, result in self.checksum_refs.get(checksum, set()):
            if isinstance(refholder, Cell):
                cell = refholder
                has_cell = True
                if cell._hash_pattern:
                    is_deep = True
                c_remote = rmap[cell._fingertip_remote]
                remote = min(remote, c_remote)
                c_recompute = rmap[cell._fingertip_recompute]
                recompute = min(recompute, c_recompute)
                break

        if must_have_cell and not has_cell:
            raise CacheMissError(checksum.hex())

        if recompute - remote in (0, 1) and remote > 0:
            buffer_info = buffer_cache.get_buffer_info(checksum, sync_remote=True, buffer_from_remote=False, force_length=False)
            if buffer_info.get("length", 0) <= RECOMPUTE_OVER_REMOTE:
                remote = recompute + 1

        if remote > recompute:
            buffer = get_buffer(checksum, remote=True, deep=is_deep)
            if buffer is not None:
                return buffer

        for tf_checksum in tf_cache.known_transformations_rev.get(checksum, []):
            if tf_checksum.hex() in TRANSFORMATION_STACK:
                continue
            transformation = tf_cache.transformations.get(tf_checksum)
            if transformation is None:
                buffer = get_buffer(tf_checksum, remote=True)
                if buffer is None:
                    continue
                transformation = await DeserializeBufferTask(
                    manager, buffer, tf_checksum, "plain", copy=True
                ).run()
                if transformation is None:
                    continue
            coros.append(fingertip_transformation(transformation, tf_checksum))

        for refholder, result in self.checksum_refs.get(checksum, set()):
            if not result:
                continue
            if isinstance(refholder, Expression):
                coros.append(fingertip_expression(refholder))
            elif isinstance(refholder, Transformer) and recompute:
                tf_checksum = tf_cache.transformer_to_transformations[refholder]
                if tf_checksum.hex() in TRANSFORMATION_STACK:
                    continue
                transformation = tf_cache.transformations[tf_checksum]
                coros.append(fingertip_transformation(transformation, tf_checksum))

        async def buffer_from_syn2sem(checksum, syn_checksum, celltype, subcelltype):
            await syntactic_to_semantic(syn_checksum, celltype, subcelltype, "fingertip")
            return get_buffer(checksum, remote=False)

        if checksum in self.rev_join_cache:
            join_dict = self.rev_join_cache[checksum]
            coro = fingertip_join(checksum, join_dict)
            coros.append(coro)

        if not len(coros):

            syn_checksums = None
            semkeys = (checksum, "python", None), (checksum, "python", "transformer")
            for semkey in semkeys:
                syn_checksums = self.transformation_cache.semantic_to_syntactic_checksums.get(semkey)
                if syn_checksums:
                    break
                syn_checksums = database.get_sem2syn(semkey)
                if syn_checksums:
                    break

            if not syn_checksums:
                sem2syn = self.transformation_cache.semantic_to_syntactic_checksums
                for (sem_checksum, celltype, subcelltype), syn_checksums0 in sem2syn.items():
                    if sem_checksum == checksum:
                        syn_checksums = syn_checksums0
                        break
            
            if syn_checksums:
                for syn_checksum in syn_checksums:
                    coro = buffer_from_syn2sem(checksum, syn_checksum, celltype, subcelltype)
                    coros.append(coro)

        if not len(coros):
            # Heroic attempt to get a reverse conversion from any buffer_info
            # This extends a much simpler buffer_info effort in get_buffer.py
            attr_list = (
                "str2text", "text2str", "binary2bytes", "bytes2binary",
                "binary2json", "json2binary"
            )
            checksum_hex = checksum.hex()
            for source_checksum, buffer_info in buffer_cache.buffer_info.items():
                for attr in attr_list:
                    if getattr(buffer_info, attr) == checksum_hex:
                        expr_celltype, expr_target_celltype = attr.replace("json", "plain").split("2")
                        expr = Expression(
                            source_checksum, None, expr_celltype, expr_target_celltype, None,
                            hash_pattern=None, target_hash_pattern=None
                        )
                        coros.append(fingertip_expression(expr))


        all_tasks = [asyncio.ensure_future(c) for c in coros]
        try:
            tasks = all_tasks
            while len(tasks):
                _, tasks  = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                buffer = get_buffer(checksum, remote=False)
                if buffer is not None:
                    return buffer
        finally:
            for task in all_tasks:
                if task.done():
                    try:
                        task.result()
                    except Exception:
                        #import traceback; traceback.print_exc()
                        pass
                else:
                    task.cancel()

        buffer = get_buffer(checksum,remote=True)
        if buffer is not None:
            return buffer

        if remote:
            buffer = download_buffer_from_servers(checksum)
            if buffer is not None:
                return buffer
        exc_list = ["\n".join(traceback.format_exception(task.exception())) for task in all_tasks if task.exception()]
        exc_str = ""
        if len(exc_list):
            exc_str = "\nFingertip exceptions:\n\n" + "\n\n".join(exc_list)
        raise CacheMissError(checksum.hex() + exc_str)


    def decref_checksum(self, checksum, refholder, authoritative, result, *, destroying=False):
        """
        NOTE: incref/decref must happen within one async step
        Therefore, the direct or indirect call of _sync versions of coroutines
        (e.g. deserialize_sync, which launches coroutines and waits for them)
        IS NOT ALLOWED
        """
        #print("DECREF", refholder, checksum.hex())
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
            if cell._hash_pattern is not None:
                deeprefmanager.decref_deep_buffer(checksum, cell._hash_pattern, authoritative)

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
        #elif isinstance(refholder, Library):  ## yagni??
        #    pass
        else:
            raise TypeError(type(refholder))
        try:
            refh = refholder
            self.checksum_refs[checksum].remove((refh, result))
        except Exception:
            print_warning("""cachemanager: cannot remove unknown checksum ref:
checksum: {}
refholder: {}
is authoritative: {}
is result checksum: {}
""".format(checksum.hex(), refholder, authoritative, result))
            return
        #print("cachemanager DECREF", checksum.hex(), len(self.checksum_refs[checksum]))
        if len(self.checksum_refs[checksum]) == 0:
            buffer_cache.decref(checksum)
            self.checksum_refs.pop(checksum)
        
    def destroy_cell(self, cell):
        ref = self.cell_to_ref[cell]
        if ref is not None:
            checksum, authoritative = ref
            self.decref_checksum(checksum, cell, authoritative, False, destroying=True)
        self.cell_to_ref.pop(cell)

    def destroy_structured_cell(self, sc):
        for inchannel in sc.inchannels.values():
            ref = self.inchannel_to_ref[inchannel]
            if ref is not None:
                checksum = ref
                self.decref_checksum(checksum, inchannel, False, False)
            self.inchannel_to_ref.pop(inchannel)

    def destroy_transformer(self, transformer):
        ref = self.transformer_to_result_checksum[transformer]
        if ref is not None:
            checksum = ref
            self.decref_checksum(checksum, transformer, False, True)
        self.transformer_to_result_checksum.pop(transformer)
        self.transformation_cache.destroy_transformer(transformer)

    def destroy_macro(self, macro):
        self.macro_exceptions.pop(macro)

    def destroy_reactor(self, reactor):
        refs = self.reactor_to_refs.pop(reactor)
        for pinname in reactor._pins:
            if reactor._pins[pinname].io == "output":
                ref = refs[pinname]
                if ref is not None:
                    checksum = ref
                    self.decref_checksum(checksum, reactor, False, False)
        self.reactor_exceptions.pop(reactor)

    def destroy_expression(self, expression):
        # Special case, since we never actually clear expression caches,
        #  we just inactivate them if not referenced
        assert expression not in self.inactive_expressions
        ref = self.expression_to_ref[expression]
        if ref is not None:
            checksum = ref
            self.decref_checksum(checksum, expression, False, False)
        ref = self.expression_to_result_checksum[expression]
        if ref is not None and ref != expression.checksum:
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
        ok = True
        name = self.__class__.__name__
        for attrib in attribs:
            a = getattr(self, attrib)
            if attrib == "checksum_refs":
                a = [list(aa) for aa in a.values() if len(aa)]
            elif attrib.startswith("expression_to"):
                a = [aa for aa in a if aa not in self.inactive_expressions]
            if len(a):
                print_warning(name + ", " + attrib + ": %d undestroyed"  % len(a))
                ok = False

    def get_join_cache(self, join_dict):
        checksum = calculate_dict_checksum(join_dict)
        return copy.deepcopy(self.join_cache.get(checksum))

    def set_join_cache(self, join_dict, result_checksum):
        if isinstance(result_checksum, str):
            result_checksum = bytes.fromhex(result_checksum)
        if join_dict == {'inchannels': {'[]': result_checksum.hex()}}:
            return
        checksum = calculate_dict_checksum(join_dict)
        self.join_cache[checksum] = result_checksum
        self.rev_join_cache[result_checksum] = join_dict


from ..cell import Cell
from ..transformer import Transformer
from ..structured_cell import Inchannel
from .expression import Expression
from ..protocol.get_buffer import get_buffer
from ..cache.transformation_cache import syntactic_to_semantic
from ..protocol.expression import set_subpath_checksum, access_hash_pattern
from ..cache.deeprefmanager import deeprefmanager