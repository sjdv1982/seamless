# See ../protocol/conversion.py for documentation about conversions.

import traceback, asyncio
import sys
from asyncio import CancelledError

from . import Task

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
        cachemanager = self.manager().cachemanager

        locknr = await acquire_evaluation_lock(self)
        try:

            source_celltype = expression.celltype
            target_celltype = expression.target_celltype

            # Get the expression result checksum from cache.
            result_checksum = None
            from_cache = True
            if not self.fingertip_mode:
                result_checksum = \
                    cachemanager.expression_to_result_checksum.get(expression)            
            if result_checksum is None:
                source_checksum = expression.checksum
                source_hash_pattern = expression.hash_pattern
                from_cache = False
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

                ### Hash pattern equivalence. Code below is for simple hash patterns.
                # More complex hash patterns may be also be equivalent, which can be determined:
                # - Statically, e.g. {"x": "##"} == {"*": "#"}
                # - Dynamically, e.g. {"x": "#", "y": {"!": "#"} } == {"x": "#"} if y is absent in the value
                # This is to be implemented later. For now, there are no complex hash patterns in Seamless.

                hash_pattern_equivalent = False
                if source_celltype == target_celltype:
                    hash_pattern_equivalent = (result_hash_pattern == target_hash_pattern)

                ### /Hash pattern equivalence

                conversion_forbidden = False
                if result_hash_pattern in ("#", "##"):
                    source_buffer = await GetBufferTask(manager, source_checksum).run()
                    if source_buffer is None:
                        raise CacheMissError(source_checksum)
                    deep_source_value = await DeserializeBufferTask(manager, source_buffer, source_checksum, "plain", False).run()
                    mode, subpath_result = await get_subpath(deep_source_value, source_hash_pattern, expression.path)
                    if subpath_result is not None:
                        assert mode == "checksum"
                    source_checksum = subpath_result
                    source_hash_pattern = None
                    trivial_path = True

                need_buf = None
                try:
                    need_buf = needs_buffer_evaluation(
                        source_checksum,
                        source_celltype,
                        target_celltype,
                        self.fingertip_mode
                    )
                    need_value = False
                    if not trivial_path:
                        need_value = True
                    elif not hash_pattern_equivalent:
                        if source_hash_pattern is not None:
                            need_value = True
                except TypeError:     
                    conversion_forbidden = True               
                    need_value = True

                try:
                    result_buffer = None
                    # If the expression is trivial, obtain its result checksum directly                    
                    if trivial_path and hash_pattern_equivalent:
                        result_checksum = source_checksum
                    elif trivial_path and not need_value and not need_buf: 
                        result_checksum = await evaluate_from_checksum(
                            source_checksum, source_celltype,
                            target_celltype
                        )
                    else:
                        buffer = await GetBufferTask(manager, source_checksum).run()
                        if not need_value:
                            # Evaluate from buffer
                            result_checksum = await evaluate_from_buffer(
                                source_checksum, buffer,
                                source_celltype, target_celltype,
                                fingertip_mode=self.fingertip_mode
                            )
                        else:
                            # Worst case. We have to deserialize the buffer, and evaluate the expression path on that.
                            value = await DeserializeBufferTask(
                                manager, buffer, source_checksum,
                                source_celltype, copy=False
                            ).run()
                            mode, result = await get_subpath(value, source_hash_pattern, expression.path)
                            use_value = False
                            if result is None:
                                result_checksum = None
                            elif mode == "checksum":
                                assert source_hash_pattern is not None
                                if conversion_forbidden or need_buf:
                                    buffer2 = await GetBufferTask(manager, result).run()
                                if conversion_forbidden:
                                    result_value = await DeserializeBufferTask(
                                        manager, buffer2, result, source_celltype,
                                        copy=False
                                    )
                                    use_value = True
                                elif need_buf:
                                    result_checksum = await evaluate_from_buffer(
                                        result, buffer2,
                                        source_celltype, target_celltype,
                                        fingertip_mode=self.fingertip_mode
                                    )
                                else:
                                    result_checksum = await evaluate_from_checksum(
                                        result, source_celltype,
                                        target_celltype
                                    )
                            elif mode == "value":
                                use_value = True
                                result_value = result                             
                            if use_value:
                                result_buffer = await SerializeToBufferTask(
                                    manager, result_value,
                                    expression.target_celltype,
                                    use_cache=True
                                ).run()
                                if result_buffer is not None:
                                    result_checksum = await CalculateChecksumTask(
                                        manager, result_buffer
                                    ).run()

                    if target_hash_pattern not in (None, "#", "##"):
                        result_buffer = None
                        result_checksum = await apply_hash_pattern(result_checksum, target_hash_pattern)

                    if result_checksum is not None and result_buffer is not None:
                        buffer_cache.cache_buffer(result_checksum, result_buffer)

                    await validate_subcelltype(
                        result_checksum,
                        target_celltype,
                        expression.target_subcelltype,
                        codename="expression"
                    )
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
                        ###print(exc, file=sys.stderr))
                    else:
                        fexc = traceback.format_exc()
                        expression.exception = fexc
                        ###print(fexc, file=sys.stderr)
                    result_checksum = None
                    

                if not from_cache and result_checksum is not None:
                    if result_checksum != expression.checksum:
                        cachemanager.incref_checksum(
                            result_checksum,
                            expression,
                            False,
                            True
                        )
            return result_checksum
        finally:
            release_evaluation_lock(locknr)

from .get_buffer import GetBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .serialize_buffer import SerializeToBufferTask
from ..expression import Expression
from ...protocol.evaluate import needs_buffer_evaluation, evaluate_from_checksum, evaluate_from_buffer
from ...protocol.conversion import conversion_forbidden, SeamlessConversionError
from ...protocol.validate_subcelltype import validate_subcelltype
from ...protocol.expression import get_subpath
from .checksum import CalculateChecksumTask
from ...cache.buffer_cache import buffer_cache, CacheMissError
from . import acquire_evaluation_lock, release_evaluation_lock
from ...protocol.deep_structure import access_hash_pattern, apply_hash_pattern, value_to_deep_structure
from ...protocol.expression import get_subpath
