import weakref
import copy

import logging

from seamless import CacheMissError, Checksum, Buffer
from seamless.checksum.database_client import database
from seamless.checksum.buffer_cache import buffer_cache
from seamless.checksum.calculate_checksum import calculate_dict_checksum
from seamless.checksum.serialize import serialize_sync as serialize
from seamless.checksum import buffer_remote

from seamless.util import unchecksum

logger = logging.getLogger(__name__)


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


class CacheManager:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.checksum_refs = {}
        self.persistent_checksums = set()

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
            checksum = Checksum(checksum)
            if checksum:
                self.incref_checksum(checksum, expression, result=False)
            checksum = self.expression_to_result_checksum.get(expression)
            checksum = Checksum(checksum)
            if checksum and checksum != expression.checksum:
                self.incref_checksum(checksum, expression, result=True)
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

    def incref_checksum(self, checksum: Checksum, refholder, *, result):
        """
        NOTE: incref/decref must happen within one async step
        Therefore, the direct or indirect call of _sync versions of coroutines
        (e.g. deserialize_sync, which launches coroutines and waits for them)
        IS NOT ALLOWED
        """
        checksum = Checksum(checksum)
        if not checksum:
            return
        # print("INCREF CHECKSUM", checksum.hex(), refholder, result)
        incref_hash_pattern = False
        if isinstance(refholder, Cell):
            assert not result
            assert self.cell_to_ref[refholder] is None
            persistent = not refholder._scratch
            self.cell_to_ref[refholder] = checksum
            cell = refholder
            if cell._hash_pattern is not None:
                incref_hash_pattern = True
        elif isinstance(refholder, Expression):
            # print("INCREF EXPRESSION", refholder, result)
            assert refholder not in self.inactive_expressions
            persistent = False
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
            assert result
            assert self.transformer_to_result_checksum[refholder] is None
            persistent = not refholder._scratch
            self.transformer_to_result_checksum[refholder] = checksum
        elif isinstance(refholder, Inchannel):
            assert not result
            assert self.inchannel_to_ref[refholder] is None
            persistent = False
            self.inchannel_to_ref[refholder] = checksum
        # elif isinstance(refholder, Library): # yagni??
        #    pass
        else:
            raise TypeError(type(refholder))

        refh = refholder
        try:
            if checksum not in self.checksum_refs:
                self.checksum_refs[checksum] = set()
                buffer_cache.incref(checksum, persistent=persistent)
                if persistent:
                    self.persistent_checksums.add(checksum)
            elif persistent and checksum not in self.persistent_checksums:
                self.persistent_checksums.add(checksum)
                buffer_cache.incref(checksum, persistent=True)
                buffer_cache.decref(checksum)
        finally:
            item = (refh, result)
            self.checksum_refs[checksum].add(item)
        # print("cachemanager INCREF", checksum.hex(), len(self.checksum_refs[checksum]))
        if incref_hash_pattern:
            cell = refholder
            subchecksums_persistent = cell._subchecksums_persistent
            deeprefmanager.incref_deep_buffer(
                checksum,
                cell._hash_pattern,
                cell=cell,
                subchecksums_persistent=subchecksums_persistent,
            )

    async def fingertip(
        self, checksum, *, dunder=None, must_have_cell=False
    ) -> bytes | None:
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
        return await self._fingertip(
            checksum, dunder=dunder, must_have_cell=must_have_cell, done=set()
        )

    def _mine_database(self, checksum: Checksum):
        result_expressions = []
        result_joins = []
        result_transformations = []

        expressions = database.get_rev_expression(checksum)
        if expressions is not None:
            for expression in expressions:
                result = expression.pop("result")
                assert result == checksum.hex(), (result, checksum.hex())
                expression["target_subcelltype"] = expression.get("target_subcelltype")
                expression["checksum"] = Checksum(expression["checksum"])
                expr = Expression(**expression)
                result_expressions.append(expr)

        joins = database.get_rev_join(checksum)
        if joins is not None:
            result_joins = [Checksum(join) for join in joins]

        tfs = database.get_rev_transformations(checksum)
        if tfs is not None:
            result_transformations = [Checksum(tf) for tf in tfs]

        return result_expressions, result_joins, result_transformations

    async def _build_fingertipper(self, checksum, *, dunder=None, recompute, done):
        from .tasks.deserialize_buffer import DeserializeBufferTask
        from ..direct.run import TRANSFORMATION_STACK
        from .fingertipper import FingerTipper

        fingertipper = FingerTipper(
            checksum, self, dunder=dunder, recompute=recompute, done=done
        )

        manager = self.manager()
        tf_cache = self.transformation_cache

        async def add_transformations(tf_checksums):
            for tf_checksum in tf_checksums:
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
                fingertipper.transformations.append((transformation, tf_checksum))

        if recompute:
            tf_checksums = tf_cache.known_transformations_rev.get(checksum, [])
            tf_checksums += tf_cache.transformation_results_rev.get(checksum, [])
            await add_transformations(tf_checksums)

        for refholder, result in self.checksum_refs.get(checksum, set()):
            if not result:
                continue
            if isinstance(refholder, Expression):
                expression = refholder
                fingertipper.expressions.append(expression)
            elif isinstance(refholder, Transformer) and recompute:
                tf_checksum = tf_cache.transformer_to_transformations[refholder]
                if tf_checksum.hex() in TRANSFORMATION_STACK:
                    continue
                transformation = tf_cache.transformations[tf_checksum]
                fingertipper.transformations.append((transformation, tf_checksum))

        if checksum in self.rev_join_cache:
            join_dict = self.rev_join_cache[checksum]
            fingertipper.joins.append(join_dict)

        if fingertipper.empty:

            syn_checksums = None
            semkeys = (checksum, "python", None), (checksum, "python", "transformer")
            for semkey in semkeys:
                syn_checksums0 = (
                    self.transformation_cache.semantic_to_syntactic_checksums.get(
                        semkey
                    )
                )
                if syn_checksums0:
                    break
                syn_checksums0 = database.get_sem2syn(semkey)
                if syn_checksums0:
                    break
            if syn_checksums0:
                syn_checksums = [(cs, semkey[0], semkey[1]) for cs in syn_checksums0]

            if not syn_checksums:
                sem2syn = self.transformation_cache.semantic_to_syntactic_checksums
                for (
                    sem_checksum,
                    celltype,
                    subcelltype,
                ), syn_checksums0 in sem2syn.items():
                    if sem_checksum == checksum:
                        syn_checksums = [
                            (cs, celltype, subcelltype) for cs in syn_checksums0
                        ]
                        break

            if syn_checksums:
                for syn_checksum, celltype, subcelltype in syn_checksums:
                    fingertipper.syn2sem.append((syn_checksum, celltype, subcelltype))

        if fingertipper.empty:
            # Heroic attempt to get a reverse conversion from any buffer_info
            # This extends a much simpler buffer_info effort in get_buffer.py
            attr_list = (
                "str2text",
                "text2str",
                "binary2bytes",
                "bytes2binary",
                "binary2json",
                "json2binary",
            )
            checksum_hex = checksum.hex()
            for source_checksum, buffer_info in buffer_cache.buffer_info.items():
                for attr in attr_list:
                    if getattr(buffer_info, attr) == checksum_hex:
                        expr_celltype, expr_target_celltype = attr.replace(
                            "json", "plain"
                        ).split("2")
                        expression = Expression(
                            source_checksum,
                            None,
                            expr_celltype,
                            expr_target_celltype,
                            None,
                            hash_pattern=None,
                            target_hash_pattern=None,
                        )
                        fingertipper.expressions.append(expression)

        if fingertipper.empty and database.active:
            # Extremely heroic effort to mine a database for expressions and structured cell joins
            mined_expressions, mined_joins, mined_transformations = self._mine_database(
                checksum
            )
            fingertipper.expressions += mined_expressions
            fingertipper.joins2 += mined_joins
            await add_transformations(mined_transformations)

        return fingertipper

    async def _fingertip(
        self, checksum: Checksum, *, must_have_cell, done, dunder=None
    ) -> bytes | None:

        checksum = Checksum(checksum)
        if not checksum:
            return

        buffer = get_buffer(checksum, remote=True)
        if buffer is not None:
            return buffer
        if checksum in done:
            return

        done.add(checksum)

        remote, recompute = True, True
        is_deep = False
        has_cell = False
        for refholder, _ in self.checksum_refs.get(checksum, set()):
            if isinstance(refholder, Cell):
                cell = refholder
                has_cell = True
                if cell._hash_pattern:
                    is_deep = True
                remote = cell._fingertip_remote
                recompute = cell._fingertip_recompute
                break

        if must_have_cell and not has_cell:
            raise CacheMissError(checksum.hex())

        if remote:
            buffer = get_buffer(checksum, remote=True, deep=is_deep)
            if buffer is not None:
                print("REMOT")
                return buffer

        fingertipper = await self._build_fingertipper(
            checksum, dunder=dunder, recompute=recompute, done=done
        )

        exc_str = None
        if not fingertipper.empty:
            exc_str = await fingertipper.run()

            buffer = get_buffer(checksum, remote=remote)
            if buffer is not None:
                return buffer

        if exc_str is None:
            exc_str = ""
        raise CacheMissError(checksum.hex() + exc_str)

    def decref_checksum(
        self, checksum: Checksum, refholder, result, *, destroying=False
    ):
        """
        NOTE: incref/decref must happen within one async step
        Therefore, the direct or indirect call of _sync versions of coroutines
        (e.g. deserialize_sync, which launches coroutines and waits for them)
        IS NOT ALLOWED
        """
        # print("DECREF", refholder, checksum.hex())
        checksum = Checksum(checksum)
        if checksum not in self.checksum_refs:
            if not checksum:
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
                deeprefmanager.decref_deep_buffer(checksum, cell._hash_pattern)

        elif isinstance(refholder, Expression):
            # Special case, since we never actually clear expression caches,
            #  we just inactivate them if not referenced
            # print("DECREF EXPRESSION", refholder._get_hash(), result)
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
        # elif isinstance(refholder, Library):  ## yagni??
        #    pass
        else:
            raise TypeError(type(refholder))
        try:
            refh = refholder
            self.checksum_refs[checksum].remove((refh, result))
        except Exception:
            print_warning(
                """cachemanager: cannot remove unknown checksum ref:
checksum: {}
refholder: {}
is result checksum: {}
""".format(
                    checksum.hex(), refholder, result
                )
            )
            return
        # print("cachemanager DECREF", checksum.hex(), len(self.checksum_refs[checksum]))
        if len(self.checksum_refs[checksum]) == 0:
            buffer_cache.decref(checksum)
            self.checksum_refs.pop(checksum)
            if checksum in self.persistent_checksums:
                self.persistent_checksums.remove(checksum)

    def destroy_cell(self, cell):
        checksum = self.cell_to_ref[cell]
        if checksum:
            self.decref_checksum(checksum, cell, False, destroying=True)
        self.cell_to_ref.pop(cell)

    def destroy_structured_cell(self, sc):
        for inchannel in sc.inchannels.values():
            ref = self.inchannel_to_ref[inchannel]
            if ref is not None:
                checksum = ref
                self.decref_checksum(checksum, inchannel, False)
            self.inchannel_to_ref.pop(inchannel)

    def destroy_transformer(self, transformer):
        ref = self.transformer_to_result_checksum[transformer]
        if ref is not None:
            checksum = ref
            self.decref_checksum(checksum, transformer, True)
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
                    self.decref_checksum(checksum, reactor, False)
        self.reactor_exceptions.pop(reactor)

    def destroy_expression(self, expression):
        # Special case, since we never actually clear expression caches,
        #  we just inactivate them if not referenced
        assert expression not in self.inactive_expressions
        ref = self.expression_to_ref[expression]
        if ref is not None:
            checksum = ref
            self.decref_checksum(checksum, expression, False)
        ref = self.expression_to_result_checksum[expression]
        if ref is not None and ref != expression.checksum:
            checksum = ref
            self.decref_checksum(checksum, expression, True)
        self.inactive_expressions.add(expression)

    def check_destroyed(self):
        attribs = (
            "checksum_refs",
            "cell_to_ref",
            "expression_to_ref",
            "expression_to_result_checksum",
            "transformer_to_result_checksum",
            "reactor_to_refs",
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
                print_warning(name + ", " + attrib + ": %d undestroyed" % len(a))
                ok = False

    def get_join_cache(self, join_dict):
        join_dict2 = unchecksum(join_dict)
        checksum = calculate_dict_checksum(join_dict2)
        return copy.deepcopy(self.join_cache.get(checksum))

    def set_join_cache(self, join_dict, result_checksum: Checksum):
        result_checksum = Checksum(result_checksum)
        join_dict2 = unchecksum(join_dict)
        if join_dict2 == {"inchannels": {"[]": result_checksum.hex()}}:
            return
        join_dict_buf = serialize(join_dict2, "plain", use_cache=True)
        checksum = Buffer(join_dict_buf).get_checksum()
        self.join_cache[checksum] = result_checksum
        self.rev_join_cache[result_checksum] = join_dict
        buffer_cache.cache_buffer(checksum, join_dict_buf)
        buffer_cache.guarantee_buffer_info(
            checksum, "plain", buffer=join_dict_buf, sync_to_remote=True
        )
        if database.active:
            buffer_remote.write_buffer(checksum, join_dict_buf)
            database.set_structured_cell_join(
                result_checksum=result_checksum, join_checksum=checksum
            )


from ..cell import Cell
from ..transformer import Transformer
from ..structured_cell import Inchannel
from seamless.checksum import Expression
from seamless.checksum.get_buffer import get_buffer
from ..cache.deeprefmanager import deeprefmanager
