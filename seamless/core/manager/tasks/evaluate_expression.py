import traceback, asyncio
import sys

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
        self._dependencies.append(expression)

    async def _run(self):
        expression = self.expression
        if expression.checksum is None:
            return None

        manager = self.manager()
        cachemanager = self.manager().cachemanager

        locknr = await acquire_evaluation_lock(self)
        try:

            # Get the expression result checksum from cache.
            expression_result_checksum = None
            from_cache = True
            if not self.fingertip_mode:
                expression_result_checksum = \
                    cachemanager.expression_to_result_checksum.get(expression)
            if expression_result_checksum is None:
                from_cache = False
                trivial_path = (expression.path is None or expression.path == [] or expression.path == ())
                if expression.target_celltype == "checksum":
                    need_buf = needs_buffer_evaluation(
                        expression.checksum,
                        expression.celltype,
                        expression.target_celltype,
                        self.fingertip_mode
                    )
                try:
                    # If the expression is trivial, obtain its result checksum directly
                    if trivial_path and \
                    expression.hash_pattern is None and \
                    not needs_buffer_evaluation(
                        expression.checksum,
                        expression.celltype,
                        expression.target_celltype,
                        self.fingertip_mode
                    ) :
                        expression_result_checksum = await evaluate_from_checksum(
                            expression.checksum, expression.celltype,
                            expression.target_celltype
                        )
                    elif trivial_path and expression.hash_pattern is not None and expression.target_celltype == "checksum":
                        if expression.hash_pattern is None:
                            expression_result_checksum = await evaluate_from_checksum(
                                expression.checksum, expression.celltype,
                                expression.target_celltype
                            )
                        else:
                            expression_result_checksum = expression.checksum
                    else:
                        buffer = await GetBufferTask(manager, expression.checksum).run()
                        # We can evaluate from buffer, but only if:
                        # - The expression path is trivial
                        # - There is no hash pattern OR the target cell is mixed
                        #   (In which case, the expression will have a result_hash_pattern that
                        #    will be taken into account by the accessor)
                        if (trivial_path and
                        (expression.hash_pattern is None or expression.target_celltype == "mixed")
                        ):
                            expression_result_checksum = await evaluate_from_buffer(
                                expression.checksum, buffer,
                                expression.celltype, expression.target_celltype,
                                fingertip_mode=self.fingertip_mode
                            )
                        else:
                            # Worst case. We have to deserialize the buffer, and evaluate the expression path on that.
                            assert expression.celltype == "mixed" # paths may apply only to mixed cells
                            value = await DeserializeBufferTask(
                                manager, buffer, expression.checksum,
                                expression.celltype, copy=False
                            ).run()
                            mode, result = await get_subpath(value, expression.hash_pattern, expression.path)
                            if mode == "checksum":
                                if expression.target_celltype == "mixed":
                                    assert expression.result_hash_pattern == "#", expression.result_hash_pattern
                                expression_result_checksum = result
                                result_buffer = None
                            elif result is None:
                                expression_result_checksum = None
                            else:
                                result_value = result
                                result_buffer = await SerializeToBufferTask(
                                    manager, result_value,
                                    expression.target_celltype,
                                    use_cache=True
                                ).run()
                                expression_result_checksum = await CalculateChecksumTask(
                                    manager, result_buffer
                                ).run()
                            if expression_result_checksum is not None and result_buffer is not None:
                                buffer_cache.cache_buffer(expression_result_checksum, result_buffer)

                        await validate_subcelltype(
                            expression_result_checksum,
                            expression.target_celltype,
                            expression.target_subcelltype,
                            codename="expression"
                        )
                except asyncio.CancelledError as exc:
                    if self._canceled:
                        raise exc from None
                    else:
                        fexc = traceback.format_exc()
                        expression.exception = fexc
                except Exception as exc:
                    if isinstance(exc, (CacheMissError, SeamlessConversionError)):
                        expression.exception = str(exc)
                        ###print(exc, file=sys.stderr))
                    else:
                        fexc = traceback.format_exc()
                        expression.exception = fexc
                        ###print(fexc, file=sys.stderr)

                    """
                    if isinstance(exc, (CacheMissError, SeamlessConversionError)):
                        print(exc)
                    else:
                        traceback.print_exc()
                    """

                if not from_cache and expression_result_checksum is not None:
                    if expression_result_checksum != expression.checksum:
                        cachemanager.incref_checksum(
                            expression_result_checksum,
                            expression,
                            False,
                            True
                        )
            return expression_result_checksum
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