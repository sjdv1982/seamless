# See ../protocol/conversion.py for documentation about conversions.


import functools
import traceback, asyncio
import warnings
import numpy as np

from . import Task
from silk.json_util import json_encode

celltype_mapping = {
    "silk": "mixed",
    "transformer": "python",
    "reactor": "python",
    "macro": "python",
}

async def inter_deepcell_conversion(manager, value, source_hash_pattern, target_hash_pattern):
    #{"*": "#"}, {"!": "#"}, {"*": "##"}
    if source_hash_pattern == {"*": "#"} and target_hash_pattern == {"!": "#"}:
        result = [value[k] for k in sorted(value.keys())]
    elif source_hash_pattern == {"*": "#"} and target_hash_pattern == {"*": "##"}:
        result = {}
        for k in value:
            source_checksum = value[k]
            if source_checksum is not None:
                assert isinstance(source_checksum, bytes)
            target_checksum = try_convert(source_checksum, "mixed", "bytes")
            if target_checksum is None:
                raise CacheMissError(target_checksum)
            assert isinstance(target_checksum, bytes)
            result[k] = target_checksum
    elif source_hash_pattern == {"!": "#"} and target_hash_pattern == {"*": "#"}:
        result = {k:v for k,v in enumerate(value)}
    elif source_hash_pattern == {"!": "#"} and target_hash_pattern == {"*": "##"}:
        result = {}
        for k, source_checksum in enumerate(value):
            assert isinstance(source_checksum, bytes)
            target_checksum = try_convert(source_checksum, "mixed", "bytes")
            if target_checksum is None:
                raise CacheMissError(target_checksum)
            assert isinstance(target_checksum, bytes)
            result[k] = target_checksum
    elif source_hash_pattern == {"*": "##"} and target_hash_pattern == {"*": "#"}:
        result = {}
        for k in value:
            source_checksum = value[k]
            assert isinstance(source_checksum, bytes)
            target_checksum = try_convert(source_checksum, "bytes", "mixed")
            if target_checksum is None:
                raise CacheMissError(target_checksum)
            assert isinstance(target_checksum, bytes)
            result[k] = target_checksum
    elif source_hash_pattern == {"*": "##"} and target_hash_pattern == {"!": "#"}:
        result = []
        for k in sorted(value.keys()):
            source_checksum = value[k]
            assert isinstance(source_checksum, bytes)
            target_checksum = try_convert(source_checksum, "bytes", "mixed")
            if target_checksum is None:
                raise CacheMissError(target_checksum)
            assert isinstance(target_checksum, bytes)
            result.append(target_checksum)
    else:
        result = None
    return result


async def value_conversion(
    checksum, source_celltype, target_celltype, *, 
    manager, fingertip_mode
):
    cachemanager = manager.cachemanager
    if target_celltype == "checksum":
        target_buffer = checksum.hex().encode()
        target_checksum = await CalculateChecksumTask(manager, target_buffer).run()
        buffer_cache.cache_buffer(target_checksum, target_buffer)
        return target_checksum
    if source_celltype == "checksum":
        if fingertip_mode:
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
                raise SeamlessConversionError("Cannot convert deep cell in value conversion")
        checksum2 = bytes.fromhex(checksum_text)
        #return try_convert(checksum2, "bytes", target_celltype) # No, for now trust the "checksum" type
        return checksum2

    if fingertip_mode:
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
            target_value = json_encode(source_value)
        elif conv == ("plain", "binary"):
            try:
                if isinstance(source_value, (int, float, bool)):
                    target_value = np.array(source_value)
                    buffer_cache.update_buffer_info(checksum, "is_json_numeric_scalar", True)
                else:         
                    if not isinstance(source_value, list):
                        raise ValueError(msg)
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")  
                        target_value = np.array(source_value)
                        if target_value.dtype == object:
                            raise ValueError(msg)
                    buffer_cache.update_buffer_info(checksum, "is_json_numeric_array", True)
            except ValueError as exc:
                buffer_cache.update_buffer_info(checksum, "is_json_numeric_scalar", False, update_remote=False)
                buffer_cache.update_buffer_info(checksum,"is_json_numeric_array", False)
                raise exc from None
        else:
            raise AssertionError(conv)
    except Exception as exc:
        msg0 = "%s cannot be converted from %s to %s"
        msg = msg0 % (checksum.hex(), source_celltype, target_celltype)
        full_msg = msg + "\n\nOriginal exception:\n\n" + str(exc)
        raise SeamlessConversionError(full_msg) from None
    target_buffer = await SerializeToBufferTask(
        manager, target_value, target_celltype
    ).run()
    target_checksum = await CalculateChecksumTask(manager, buffer).run()
    if target_checksum is None:
        raise Exception
    assert isinstance(target_checksum, bytes)    
    buffer_cache.cache_buffer(target_checksum, target_buffer)
    if conv == ("plain", "binary"):
        buffer_cache.update_buffer_info(target_checksum, "shape", target_value.shape, update_remote=False)
        buffer_cache.update_buffer_info(target_checksum, "dtype", str(target_value.dtype))
        buffer_cache.update_buffer_info(checksum, "json2binary", target_checksum)
        buffer_cache.update_buffer_info(target_checksum, "binary2json", checksum)
    elif conv == ("binary", "plain"): 
        buffer_cache.update_buffer_info(checksum, "binary2json", target_checksum)
        buffer_cache.update_buffer_info(target_checksum, "json2binary", checksum)
    buffer_cache.guarantee_buffer_info(target_checksum, target_celltype)
    return target_checksum


async def _evaluate_expression(self, expression, manager, fingertip_mode):
    # Get the expression result checksum from cache.
    cachemanager = manager.cachemanager    
    if not fingertip_mode:
        result_checksum = \
            cachemanager.expression_to_result_checksum.get(expression)
        if result_checksum is not None:
            assert isinstance(result_checksum, bytes)
            return result_checksum

    locknr = await acquire_evaluation_lock(self)
    try:
        result_checksum = None
        result_buffer = None
        result_value = None
        source_checksum = expression.checksum
        assert isinstance(source_checksum, bytes)
        source_hash_pattern = expression.hash_pattern
        source_celltype = expression.celltype
        source_celltype = celltype_mapping.get(source_celltype, source_celltype)
        target_celltype = expression.target_celltype
        target_celltype = celltype_mapping.get(target_celltype, target_celltype)

        trivial_path = (expression.path is None or expression.path == [] or expression.path == ())
        result_hash_pattern = expression.result_hash_pattern          
        target_hash_pattern = expression.target_hash_pattern

        if result_hash_pattern not in (None, "#", "##") and target_celltype == "checksum":
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
                raise SeamlessConversionError(msg.format(source_celltype, target_celltype))

            ### Hash pattern equivalence. Code below is for simple hash patterns.
            # More complex hash patterns may be also be equivalent, which can be determined:
            # - Statically, e.g. {"x": "##"} == {"*": "#"}
            # - Dynamically, e.g. {"x": "#", "y": {"!": "#"} } == {"x": "#"} if y is absent in the value
            # This is to be implemented later. For now, there are no complex hash patterns in Seamless.

            hash_pattern_equivalent = False
            if source_celltype == target_celltype:
                hash_pattern_equivalent = (result_hash_pattern == target_hash_pattern)

            ### /Hash pattern equivalence

            if result_hash_pattern in ("#", "##"):
                if fingertip_mode:
                    source_buffer = await GetBufferTask(manager, source_checksum).run()
                else:
                    source_buffer = await cachemanager.fingertip(source_checksum)
                if source_buffer is None:
                    raise CacheMissError(source_checksum)
                deep_source_value = await DeserializeBufferTask(manager, source_buffer, source_checksum, "plain", False).run()
                mode, subpath_result = await get_subpath(deep_source_value, source_hash_pattern, expression.path)
                if subpath_result is not None:
                    assert mode == "checksum"
                source_checksum = subpath_result
                if source_checksum is not None:
                    assert isinstance(source_checksum, bytes)
                result_hash_pattern = None
                trivial_path = True

            if source_celltype == "checksum" and target_celltype == "checksum":
                result_checksum = source_checksum
                done = True
                needs_value_conversion = False
            elif source_celltype == "checksum" and target_hash_pattern is not None:
                if fingertip_mode:
                    buffer = await GetBufferTask(manager, source_checksum).run()
                else:
                    buffer = await cachemanager.fingertip(source_checksum)
                if buffer is None:
                    raise CacheMissError(source_checksum)
                deep_structure = await DeserializeBufferTask(
                    manager, buffer, source_checksum, "checksum", copy=False
                ).run()
                if isinstance(deep_structure, str):
                    raise Exception("Checksum cell does not refer to a deep cell structure")
                validate_checksum(deep_structure)
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
                        fingertip_mode=fingertip_mode
                    )            
                    result_checksum = await conversion(
                        source_checksum, source_celltype,
                        target_celltype, fingertip_mode=fingertip_mode,
                        value_conversion_callback=value_conversion_callback
                    )
                    if result_checksum is not None:
                        assert isinstance(result_checksum, bytes), result_checksum
                done = False  # still need to account for target hash pattern
                needs_value_conversion = False
            elif trivial_path and hash_pattern_equivalent: #deepcell-to-deepcell
                result_checksum = source_checksum
                done = True
                needs_value_conversion = False
            else:
                needs_value_conversion = True

            if needs_value_conversion:
                if fingertip_mode:
                    buffer = await GetBufferTask(manager, source_checksum).run()
                else:
                    buffer = await cachemanager.fingertip(source_checksum)
                value = await DeserializeBufferTask(
                    manager, buffer, source_checksum,
                    source_celltype, copy=False
                ).run()
                full_value = True
                if trivial_path:
                    result_value = await inter_deepcell_conversion(
                        manager, value, 
                        source_hash_pattern, target_hash_pattern
                    )
                    if result_value is not None:
                        full_value = False
                if full_value:
                    mode, result = await get_subpath(value, source_hash_pattern, expression.path)
                    assert mode in ("checksum", "value"), mode
                    if result is None:
                        done = True
                        result_checksum = None
                    elif mode == "checksum":
                        assert source_hash_pattern is not None
                        if fingertip_mode:
                            buffer2 = await GetBufferTask(manager, result).run()
                        else:
                            buffer2 = await cachemanager.fingertip(result)
                        if buffer2 is None:
                            raise CacheMissError(result)
                        result_value = await DeserializeBufferTask(
                            manager, buffer2, result, source_celltype,
                            copy=False
                        )
                    elif mode == "value":
                        use_value = True                    
                        result_value = result                             

                if (not done) and use_value:
                    result_checksum = None
                    result_buffer = await SerializeToBufferTask(
                        manager, result_value,
                        expression.target_celltype,
                        use_cache=True
                    ).run()
                    if result_buffer is not None:
                        result_checksum = await CalculateChecksumTask(
                            manager, result_buffer
                        ).run()
                        if result_checksum is None:
                            raise Exception
                        assert isinstance(result_checksum, bytes)
                    done = True

            if not done and target_hash_pattern not in (None, "#", "##"):
                result_checksum = await apply_hash_pattern(result_checksum, target_hash_pattern)
                if result_checksum is not None:
                    assert isinstance(result_checksum, bytes)

        except asyncio.CancelledError as exc:
            if self._canceled:
                raise exc from None
            else:
                fexc = traceback.format_exc()
                expression.exception = fexc
            result_checksum = None
        except Exception as exc:
            if isinstance(exc, (CacheMissError, SeamlessConversionError)):
                expression.exception = str(exc)
                if isinstance(exc, CacheMissError):
                    expression.exception = "CacheMissError: " + expression.exception
                ###print(exc, file=sys.stderr))
            else:
                fexc = traceback.format_exc()
                expression.exception = fexc
                ###print(fexc, file=sys.stderr)
            result_checksum = None
            
        if result_checksum is not None:
            assert isinstance(result_checksum, bytes)
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
                            codename="expression"
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

            if result_checksum != expression.checksum:
                cachemanager.incref_checksum(
                    result_checksum,
                    expression,
                    authoritative=False,
                    result=True
                )

        cachemanager.expression_to_result_checksum[expression] = result_checksum
        return result_checksum
    finally:
        release_evaluation_lock(locknr)

class EvaluateExpressionTask(Task):
    """ Evaluates an expression
    Fingertip mode is True only if the task is triggered from cachemanager.fingertip,
     as part of a reverse provenance recomputation
    """
    @property
    def refkey(self):
        return (self.expression, self.fingertip_mode)

    def __init__(self, manager, expression, *, fingertip_mode=False):
        assert isinstance(expression, Expression)
        self.expression = expression
        self.fingertip_mode = fingertip_mode
        super().__init__(manager)
        if not self.fingertip_mode:
            self._dependencies.append(expression)

    async def _run(self):
        expression = self.expression
        if expression.checksum is None:
            return None

        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        return await _evaluate_expression(self, expression, manager, self.fingertip_mode)

async def evaluate_expression(expression):
    manager = Manager()
    result = await EvaluateExpressionTask(manager, expression).run()
    return result

from .get_buffer import GetBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .serialize_buffer import SerializeToBufferTask
from ..expression import Expression
from ...protocol.evaluate import conversion, validate_checksum, try_convert, validate_evaluation_subcelltype
from ...conversion import SeamlessConversionError, conversion_forbidden
from ...protocol.expression import get_subpath
from .checksum import CalculateChecksumTask
from ...cache.buffer_cache import buffer_cache, CacheMissError
from . import acquire_evaluation_lock, release_evaluation_lock
from ...protocol.deep_structure import access_hash_pattern, apply_hash_pattern, value_to_deep_structure
from ...protocol.expression import get_subpath
from ..manager import Manager