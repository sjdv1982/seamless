# See ../protocol/conversion.py for documentation about conversions.


import functools
import traceback, asyncio
import warnings

from . import Task

from seamless import Checksum, Buffer

celltype_mapping = {
    "silk": "mixed",
    "transformer": "python",
    "reactor": "python",
    "macro": "python",
}


async def inter_deepcell_conversion(value, source_hash_pattern, target_hash_pattern):
    # {"*": "#"}, {"!": "#"}, {"*": "##"}
    if source_hash_pattern == {"*": "#"} and target_hash_pattern == {"!": "#"}:
        result = [value[k] for k in sorted(value.keys())]
    elif source_hash_pattern == {"*": "#"} and target_hash_pattern == {"*": "##"}:
        result = {}
        for k in value:
            source_checksum = Checksum(value[k])
            target_checksum = try_convert(source_checksum, "mixed", "bytes")
            if target_checksum is None:
                raise CacheMissError(target_checksum)
            assert isinstance(target_checksum, Checksum)
            result[k] = target_checksum
    elif source_hash_pattern == {"!": "#"} and target_hash_pattern == {"*": "#"}:
        result = {k: v for k, v in enumerate(value)}
    elif source_hash_pattern == {"!": "#"} and target_hash_pattern == {"*": "##"}:
        result = {}
        for k, source_checksum in enumerate(value):
            assert isinstance(source_checksum, bytes)
            target_checksum = try_convert(source_checksum, "mixed", "bytes")
            if target_checksum is None:
                raise CacheMissError(target_checksum)
            assert isinstance(target_checksum, Checksum)
            result[k] = target_checksum
    elif source_hash_pattern == {"*": "##"} and target_hash_pattern == {"*": "#"}:
        result = {}
        for k in value:
            source_checksum = value[k]
            assert isinstance(source_checksum, bytes)
            target_checksum = try_convert(source_checksum, "bytes", "mixed")
            if target_checksum is None:
                raise CacheMissError(target_checksum)
            assert isinstance(target_checksum, Checksum)
            result[k] = target_checksum
    elif source_hash_pattern == {"*": "##"} and target_hash_pattern == {"!": "#"}:
        result = []
        for k in sorted(value.keys()):
            source_checksum = value[k]
            assert isinstance(source_checksum, bytes)
            target_checksum = try_convert(source_checksum, "bytes", "mixed")
            if target_checksum is None:
                raise CacheMissError(target_checksum)
            assert isinstance(target_checksum, Checksum)
            result.append(target_checksum)
    else:
        result = None
    return result


async def value_conversion(
    checksum: Checksum, source_celltype, target_celltype, *, manager, perform_fingertip
):
    checksum = Checksum(checksum)
    cachemanager = manager.cachemanager
    if target_celltype == "checksum":
        target_buffer = Checksum(checksum).hex().encode()
        target_checksum = await CalculateChecksumTask(manager, target_buffer).run()
        buffer_cache.cache_buffer(target_checksum, target_buffer)
        return target_checksum
    if source_celltype == "checksum":
        if perform_fingertip:
            buffer = await GetBufferTask(manager, checksum).run()
        else:
            buffer = await cachemanager.fingertip(checksum)
        if buffer is None:
            raise CacheMissError(checksum)
        checksum_text = await DeserializeBufferTask(
            manager, buffer, checksum, "checksum", copy=False
        ).run()
        validate_checksum(checksum_text)
        if not isinstance(checksum_text, str):
            if target_celltype == "plain":
                return checksum
            else:
                raise SeamlessConversionError(
                    "Cannot convert deep cell in value conversion"
                )
        checksum2 = Checksum(checksum_text)
        # return try_convert(checksum2, "bytes", target_celltype) # No, for now trust the "checksum" type
        return checksum2

    if perform_fingertip:
        buffer = await GetBufferTask(manager, checksum).run()
    else:
        buffer = await cachemanager.fingertip(checksum)
    if buffer is None:
        raise CacheMissError(checksum)
    source_value = await DeserializeBufferTask(
        manager, buffer, checksum, source_celltype, copy=False
    ).run()
    msg = buffer
    if len(msg) > 1000:
        msg = msg[:920] + "..." + msg[-50:]
    conv = (source_celltype, target_celltype)
    try:
        if conv == ("binary", "plain"):
            from silk.json_util import json_encode

            target_value = json_encode(source_value)
        elif conv == ("plain", "binary"):
            try:
                import numpy as np

                if isinstance(source_value, (int, float, bool)):

                    target_value = np.array(source_value)
                    buffer_cache.update_buffer_info(
                        checksum, "is_json_numeric_scalar", True, sync_remote=True
                    )
                else:
                    if not isinstance(source_value, list):
                        raise ValueError(msg)
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        target_value = np.array(source_value)
                        if target_value.dtype == object:
                            raise ValueError(msg)
                    buffer_cache.update_buffer_info(
                        checksum, "is_json_numeric_array", True, sync_remote=True
                    )
            except ValueError as exc:
                buffer_cache.update_buffer_info(
                    checksum, "is_json_numeric_scalar", False, sync_remote=False
                )
                buffer_cache.update_buffer_info(
                    checksum, "is_json_numeric_array", False, sync_remote=True
                )
                raise exc from None
        else:
            raise AssertionError(conv)
    except Exception as exc:
        msg0 = "%s cannot be converted from %s to %s"
        msg = msg0 % (checksum.hex(), source_celltype, target_celltype)
        full_msg = msg + "\n\nOriginal exception:\n\n" + str(exc)
        raise SeamlessConversionError(full_msg) from None
    target_buffer = await SerializeToBufferTask(
        manager, target_value, target_celltype, use_cache=True
    ).run()
    target_checksum = await CalculateChecksumTask(manager, buffer).run()
    target_checksum = Checksum(target_checksum)
    if not target_checksum:
        raise ValueError("Unknown error")
    buffer_cache.cache_buffer(target_checksum, target_buffer)
    if conv == ("plain", "binary"):
        buffer_cache.update_buffer_info(
            target_checksum, "shape", target_value.shape, sync_remote=False
        )
        buffer_cache.update_buffer_info(
            target_checksum, "dtype", str(target_value.dtype), sync_remote=False
        )
        buffer_cache.update_buffer_info(
            target_checksum, "binary2json", checksum, sync_remote=False
        )
        buffer_cache.update_buffer_info(
            checksum, "json2binary", target_checksum, sync_remote=True
        )
    elif conv == ("binary", "plain"):
        buffer_cache.update_buffer_info(
            checksum, "binary2json", target_checksum, sync_remote=True
        )
        buffer_cache.update_buffer_info(
            target_checksum, "json2binary", checksum, sync_remote=False
        )
    buffer_cache.guarantee_buffer_info(
        target_checksum, target_celltype, sync_to_remote=True
    )
    return target_checksum


def build_expression_transformation(expression: "Expression"):
    """Creates a pseudo-transformation dict of the expression
    A pseudo-transformation is a transformation with language "<expression>"
    that in fact performs an expression evaluation.
    The main use case is to send data-intensive expressions to remote locations
    where the data is.
    """

    expression_dict = {
        "checksum": expression.checksum.hex(),
        "celltype": expression.celltype,
        "path": expression.path,
        "target_celltype": expression.target_celltype,
    }
    if expression.hash_pattern is not None:
        expression_dict["hash_pattern"] = expression.hash_pattern
    if expression.target_hash_pattern is not None:
        expression_dict["target_hash_pattern"] = expression.target_hash_pattern

    transformation_dict = {
        "__language__": "<expression>",
        "expression": expression_dict,
    }

    transformation_dict_buffer = Buffer(transformation_dict, "plain")
    transformation = transformation_dict_buffer.get_checksum()
    buffer_cache.cache_buffer(transformation, transformation_dict_buffer)
    return transformation


async def evaluate_expression_remote(expression, fingertip_mode) -> Checksum | None:
    from seamless.config import get_assistant
    from seamless.assistant_client import run_job
    from seamless.checksum.buffer_remote import write_buffer

    if not get_assistant():
        return
    etf_checksum = build_expression_transformation(expression)
    etf_buffer = await buffer_cache.get_buffer_async(etf_checksum)
    assert etf_buffer is not None
    write_buffer(etf_checksum, etf_buffer)
    try:
        result = await run_job(
            etf_checksum, tf_dunder=None, scratch=True, fingertip=fingertip_mode
        )
        result = Checksum(result)
        if result and fingertip_mode:
            result = await buffer_cache.get_buffer_async(result)
    except (CacheMissError, RuntimeError):
        result = None
    return result


async def _evaluate_expression(
    self, expression, *, manager, fingertip_mode, fingertip_upstream, fingertip_done
):
    cachemanager = manager.cachemanager
    if not fingertip_mode:
        result_checksum = cachemanager.expression_to_result_checksum.get(expression)
        result_checksum = Checksum(result_checksum)
        if result_checksum:
            return result_checksum

    perform_fingertip = fingertip_mode or fingertip_upstream

    locknr = await acquire_evaluation_lock(self)
    try:
        result_checksum = None
        result_buffer = None
        result_value = None
        source_checksum = Checksum(expression.checksum)

        source_hash_pattern = expression.hash_pattern
        source_celltype = expression.celltype
        source_celltype = celltype_mapping.get(source_celltype, source_celltype)
        target_celltype = expression.target_celltype
        target_celltype = celltype_mapping.get(target_celltype, target_celltype)

        trivial_path = (
            expression.path is None or expression.path == [] or expression.path == ()
        )
        result_hash_pattern = expression.result_hash_pattern
        target_hash_pattern = expression.target_hash_pattern

        if (
            result_hash_pattern not in (None, "#", "##")
            and target_celltype == "checksum"
        ):
            # Special case. Deep cells converted to "checksum" remain unchanged
            result_hash_pattern = None
            source_celltype = "checksum"
        else:
            if result_hash_pattern == "##":
                source_celltype = "bytes"
            if target_hash_pattern == "##":
                target_celltype = "bytes"

        try:
            done = False
            conv = (source_celltype, target_celltype)
            if conv in conversion_forbidden:
                msg = "Forbidden conversion from {} to {}"
                raise SeamlessConversionError(
                    msg.format(source_celltype, target_celltype)
                )

            ### Hash pattern equivalence. Code below is for simple hash patterns.
            # More complex hash patterns may be also be equivalent, which can be determined:
            # - Statically, e.g. {"x": "##"} == {"*": "#"}
            # - Dynamically, e.g. {"x": "#", "y": {"!": "#"} } == {"x": "#"} if y is absent in the value
            # This is to be implemented later. For now, there are no complex hash patterns in Seamless.

            hash_pattern_equivalent = False
            if source_celltype == target_celltype:
                hash_pattern_equivalent = result_hash_pattern == target_hash_pattern

            ### /Hash pattern equivalence

            if result_hash_pattern in ("#", "##"):
                if perform_fingertip:
                    source_buffer = await GetBufferTask(manager, source_checksum).run()
                else:
                    release_evaluation_lock(locknr)
                    locknr = None
                    source_buffer = await cachemanager.fingertip(source_checksum)
                    locknr = await acquire_evaluation_lock(self)
                if source_buffer is None:
                    raise CacheMissError(source_checksum)
                deep_source_value = await DeserializeBufferTask(
                    manager, source_buffer, source_checksum, "plain", False
                ).run()
                mode, subpath_result = await get_subpath(
                    deep_source_value, source_hash_pattern, expression.path
                )
                if subpath_result:
                    assert mode == "checksum"
                source_checksum = subpath_result
                result_hash_pattern = None
                trivial_path = True

            if source_celltype == "checksum" and target_celltype == "checksum":
                result_checksum = source_checksum
                done = True
                needs_value_conversion = False
            elif source_celltype == "checksum" and target_hash_pattern is not None:
                assert trivial_path
                if perform_fingertip:
                    buffer = await GetBufferTask(manager, source_checksum).run()
                else:
                    release_evaluation_lock(locknr)
                    locknr = None
                    buffer = await cachemanager.fingertip(source_checksum)
                    locknr = await acquire_evaluation_lock(self)
                if buffer is None:
                    raise CacheMissError(source_checksum)
                deep_structure = await DeserializeBufferTask(
                    manager, buffer, source_checksum, "checksum", copy=False
                ).run()
                nested_checksum = None
                if isinstance(deep_structure, str):
                    nested_checksum = Checksum(deep_structure)
                    if perform_fingertip:
                        buffer = await GetBufferTask(manager, nested_checksum).run()
                    else:
                        release_evaluation_lock(locknr)
                        locknr = None
                        buffer = await cachemanager.fingertip(nested_checksum)
                        locknr = await acquire_evaluation_lock(self)
                    if buffer is None:
                        raise CacheMissError(nested_checksum)
                    deep_structure = await DeserializeBufferTask(
                        manager, buffer, nested_checksum, "checksum", copy=False
                    ).run()
                validate_checksum(deep_structure)
                validate_deep_structure(deep_structure, target_hash_pattern)

                if nested_checksum:
                    result_checksum = nested_checksum
                else:
                    result_checksum = source_checksum
                done = True
                needs_value_conversion = False
            elif trivial_path and result_hash_pattern is None:
                if source_celltype == target_celltype:
                    result_checksum = source_checksum
                else:
                    value_conversion_callback = functools.partial(
                        value_conversion,
                        manager=manager,
                        perform_fingertip=perform_fingertip,
                    )
                    release_evaluation_lock(locknr)
                    locknr = None
                    result_checksum = await conversion(
                        source_checksum,
                        source_celltype,
                        target_celltype,
                        perform_fingertip=perform_fingertip,
                        value_conversion_callback=value_conversion_callback,
                    )
                    locknr = await acquire_evaluation_lock(self)
                    result_checksum = Checksum(result_checksum)
                done = False  # still need to account for target hash pattern
                needs_value_conversion = False
            elif trivial_path and hash_pattern_equivalent:  # deepcell-to-deepcell
                result_checksum = source_checksum
                done = True
                needs_value_conversion = False
            else:
                needs_value_conversion = True

            if needs_value_conversion:
                if perform_fingertip:
                    release_evaluation_lock(locknr)
                    locknr = None
                    buffer = await cachemanager._fingertip(
                        source_checksum,
                        must_have_cell=False,
                        done=fingertip_done.copy(),
                    )
                    locknr = await acquire_evaluation_lock(self)
                else:
                    buffer = await GetBufferTask(manager, source_checksum).run()
                if buffer is None:
                    raise CacheMissError(source_checksum)
                value = await DeserializeBufferTask(
                    manager, buffer, source_checksum, source_celltype, copy=False
                ).run()
                full_value = True
                use_value = False
                if trivial_path:
                    result_value = await inter_deepcell_conversion(
                        value, source_hash_pattern, target_hash_pattern
                    )
                    if result_value is not None:
                        full_value = False
                if full_value:
                    release_evaluation_lock(locknr)
                    locknr = None
                    mode, result = await get_subpath(
                        value,
                        source_hash_pattern,
                        expression.path,
                        manager=manager,
                        perform_fingertip=perform_fingertip,
                    )
                    locknr = await acquire_evaluation_lock(self)
                    assert mode in ("checksum", "value"), mode
                    if _is_none(result):
                        done = True
                        result_checksum = None
                    elif mode == "checksum":
                        assert source_hash_pattern is not None
                        if perform_fingertip:
                            release_evaluation_lock(locknr)
                            locknr = None
                            buffer2 = await cachemanager._fingertip(
                                result, must_have_cell=False, done=fingertip_done.copy()
                            )
                            locknr = await acquire_evaluation_lock(self)
                        else:
                            buffer2 = await GetBufferTask(manager, result).run()
                        if buffer2 is None:
                            raise CacheMissError(result)
                        result_value = await DeserializeBufferTask(
                            manager, buffer2, result, source_celltype, copy=False
                        )
                    elif mode == "value":
                        use_value = True
                        result_value = result

                if (not done) and use_value:
                    if result_hash_pattern == {"*": "##"} and value is not None:
                        import numpy as np

                        for k, v in list(result_value.items()):
                            if isinstance(v, bytes):
                                result_value[k] = np.array(v, "S")
                    result_checksum = None
                    result_buffer = await SerializeToBufferTask(
                        manager,
                        result_value,
                        expression.target_celltype,
                        use_cache=True,
                    ).run()
                    if result_buffer is not None:
                        result_checksum = await CalculateChecksumTask(
                            manager, result_buffer
                        ).run()
                        if not result_checksum:
                            raise ValueError("Unknown error")
                        assert isinstance(result_checksum, Checksum)
                    done = True

            if not done and target_hash_pattern not in (None, "#", "##"):
                result_checksum = await apply_hash_pattern(
                    result_checksum, target_hash_pattern
                )

        except asyncio.CancelledError as exc:
            if self._canceled:
                raise exc from None
            else:
                fexc = traceback.format_exc()
                expression.exception = fexc
            result_checksum = None
            if locknr is None:
                locknr = await acquire_evaluation_lock(self)
        except Exception as exc:
            if isinstance(exc, (CacheMissError, SeamlessConversionError)):
                if isinstance(exc, CacheMissError):
                    expression.exception = "CacheMissError: " + str(exc)
                else:
                    expression.exception = "SeamlessConversionError: " + str(exc)
                ###print(exc, file=sys.stderr))
            else:
                fexc = traceback.format_exc()
                expression.exception = fexc
                ###print(fexc, file=sys.stderr)
            result_checksum = None
            if locknr is None:
                locknr = await acquire_evaluation_lock(self)

        result_checksum = Checksum(result_checksum)
        if result_checksum:
            if expression.target_subcelltype is not None:
                # validate subcelltype only if we can get a result buffer without heroics
                if result_buffer is None:
                    result_buffer = await GetBufferTask(manager, result_checksum).run()
                if result_buffer is not None:
                    try:
                        validate_evaluation_subcelltype(
                            result_checksum,
                            result_buffer,
                            target_celltype,
                            expression.target_subcelltype,
                            codename="expression",
                        )
                    except Exception as exc:
                        if self._canceled:
                            raise exc from None
                        else:
                            fexc = traceback.format_exc()
                            expression.exception = fexc
                        return None

            if result_buffer is not None:
                buffer_cache.cache_buffer(result_checksum, result_buffer)

            if result_checksum != expression.checksum and not fingertip_mode:
                cachemanager.incref_checksum(result_checksum, expression, result=True)

            cachemanager.expression_to_result_checksum[expression] = result_checksum
        if fingertip_mode:
            if result_buffer is None:
                release_evaluation_lock(locknr)
                locknr = None
                result_buffer = await cachemanager._fingertip(
                    result_checksum, must_have_cell=False, done=fingertip_done.copy()
                )
                locknr = await acquire_evaluation_lock(self)
            if result_buffer is None:
                return None
            return result_buffer
        else:
            return result_checksum
    finally:
        try:
            release_evaluation_lock(locknr)
        except AssertionError:
            pass


class EvaluateExpressionTask(Task):
    """Evaluates an expression
    Fingertip mode is True only if the task is triggered from cachemanager.fingertip,
     as part of a reverse provenance recomputation
    """

    @property
    def refkey(self):
        return (self.expression, self.fingertip_mode, self.fingertip_upstream)

    def __init__(
        self,
        manager,
        expression,
        *,
        fingertip_mode=False,
        fingertip_upstream=False,
        fingertip_done=None
    ):
        assert isinstance(expression, Expression)
        self.expression = expression
        self.fingertip_mode = fingertip_mode
        self.fingertip_upstream = fingertip_upstream
        if fingertip_done is None:
            fingertip_done = set()
        self.fingertip_done = fingertip_done

        super().__init__(manager)
        if not self.fingertip_mode:
            self._dependencies.append(expression)

    async def _run(self):
        expression = self.expression
        if not Checksum(expression.checksum):
            return None

        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        return await _evaluate_expression(
            self,
            expression,
            manager=manager,
            fingertip_mode=self.fingertip_mode,
            fingertip_upstream=self.fingertip_upstream,
            fingertip_done=self.fingertip_done,
        )


def _is_none(result):
    if result is None:
        return True
    elif isinstance(result, Checksum):
        return result.value is None
    else:
        return False


async def evaluate_expression(
    expression, *, fingertip_mode=False, manager=None, fingertip_done=None
):
    if fingertip_done is None:
        fingertip_done = set()
    if manager is None:
        manager = Manager()

    result = None
    if not fingertip_mode:
        result = await database.get_expression_async(expression)
    from_task = False
    if _is_none(result):
        celltype = celltype_mapping.get(expression.celltype, expression.celltype)
        target_celltype = celltype_mapping.get(
            expression.target_celltype, expression.target_celltype
        )

        if (
            expression.target_subcelltype
            and celltype == target_celltype
            and not expression.path
        ):
            assert not expression.hash_pattern and not expression.target_hash_pattern
            # validate subcelltype only if we can get a result buffer without heroics
            result_buffer = await GetBufferTask(manager, expression.checksum).run()
            if result_buffer is not None:
                try:
                    validate_evaluation_subcelltype(
                        expression.checksum,
                        result_buffer,
                        target_celltype,
                        expression.target_subcelltype,
                        codename="expression",
                    )
                except Exception:
                    fexc = traceback.format_exc()
                    expression.exception = fexc
                    return None
                if fingertip_mode:
                    result = result_buffer
                else:
                    result = expression.checksum
        if _is_none(result):
            if fingertip_mode:
                result = await evaluate_expression_remote(
                    expression, fingertip_mode=True
                )
                assert _is_none(result) or isinstance(result, bytes), type(result)
                if _is_none(result):
                    result = await EvaluateExpressionTask(
                        manager,
                        expression,
                        fingertip_mode=True,
                        fingertip_upstream=True,
                        fingertip_done=fingertip_done,
                    ).run()
                    assert _is_none(result) or isinstance(result, bytes), type(result)
                    if not _is_none(result):
                        from_task = True
            else:
                result = await EvaluateExpressionTask(
                    manager, expression, fingertip_mode=False, fingertip_upstream=False
                ).run()
                if not _is_none(result):
                    from_task = True
                else:
                    result = await evaluate_expression_remote(
                        expression, fingertip_mode=False
                    )
                    if _is_none(result):
                        result = await EvaluateExpressionTask(
                            manager,
                            expression,
                            fingertip_mode=False,
                            fingertip_upstream=True,
                            fingertip_done=fingertip_done,
                        ).run()
                        if not _is_none(result):
                            from_task = True

        if not _is_none(result):
            if fingertip_mode:
                assert isinstance(result, bytes)
                result_checksum = await CalculateChecksumTask(manager, result).run()
            else:
                result_checksum = result
            assert result_checksum
            trivial = False
            if (
                expression.path is None
                or expression.path == []
                or expression.path == ()
            ):
                if expression.hash_pattern == expression.target_hash_pattern:
                    if result_checksum == expression.checksum:
                        trivial = True
            if not trivial:
                database.set_expression(expression, result_checksum)

    if result and not from_task and not fingertip_mode:
        result = Checksum(result)
        assert result
        if result != Checksum(expression.checksum):
            manager.cachemanager.incref_checksum(result, expression, result=True)

        manager.cachemanager.expression_to_result_checksum[expression] = result

    return result


from .get_buffer import GetBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .serialize_buffer import SerializeToBufferTask
from seamless.checksum import Expression
from seamless.checksum.value_conversion import (
    conversion,
    validate_checksum,
    try_convert,
    validate_evaluation_subcelltype,
)
from seamless.checksum.conversion import SeamlessConversionError, conversion_forbidden
from ...protocol.expression import get_subpath
from .checksum import CalculateChecksumTask
from seamless.checksum.buffer_cache import buffer_cache, CacheMissError
from seamless.checksum.database_client import database
from . import acquire_evaluation_lock, release_evaluation_lock
from ...protocol.deep_structure import apply_hash_pattern, validate_deep_structure
from ..manager import Manager
