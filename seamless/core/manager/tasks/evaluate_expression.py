import traceback, asyncio

from . import Task

class EvaluateExpressionTask(Task):
    @property
    def refkey(self):
        return (self.expression, self.fingertip)

    def __init__(self, manager, expression, *, fingertip=False):
        assert isinstance(expression, Expression)
        self.expression = expression
        self.fingertip = fingertip
        super().__init__(manager)
        self.dependencies.append(expression)

    async def _run(self):
        expression = self.expression        
        if expression.checksum is None:
            return None
        
        manager = self.manager()
        cachemanager = self.manager().cachemanager
        buffer_cache = cachemanager.buffer_cache

        # Get the expression result checksum from cache.
        expression = expression
        expression_result_checksum = None
        if not self.fingertip:
            expression_result_checksum = \
                cachemanager.expression_to_checksum.get(expression)
        if expression_result_checksum is None:
            try:
                # If the expression is trivial, obtain its result checksum directly
                if expression.path is None and \
                expression.hash_pattern is None and \
                not needs_buffer_evaluation(
                    expression.checksum,
                    expression.celltype, 
                    expression.target_celltype, 
                ) :    
                    expression_result_checksum = await evaluate_from_checksum(
                        expression.checksum, expression.celltype, 
                        expression.target_celltype
                    )
                else:
                    buffer = await GetBufferTask(manager, expression.checksum).run()
                    if (
                        expression.path is None \
                        and expression.hash_pattern is None \
                    ):
                        expression_result_checksum = await evaluate_from_buffer(
                            expression.checksum, buffer, 
                            expression.celltype, expression.target_celltype,
                            buffer_cache
                        )
                    else:
                        assert expression.celltype == "mixed" # paths may apply only to mixed cells
                        value = await DeserializeBufferTask(
                            manager, buffer, expression.checksum,
                            expression.celltype, copy=False
                        ).run()
                        mode, result = await get_subpath(value, expression.hash_pattern, expression.path)
                        if mode == "value":                        
                            if result is None:
                                return None
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
                        elif mode == "checksum":
                            expression_result_checksum = result
                        else:
                            raise ValueError(mode)

                    await validate_subcelltype(
                        expression_result_checksum, 
                        expression.target_celltype, 
                        expression.target_subcelltype, 
                        codename="expression",
                        buffer_cache=buffer_cache
                    )
            except asyncio.CancelledError as exc:
                raise exc from None
            except Exception as exc:
                exc = traceback.format_exc()
                expression.exception = exc                                   
        
            if expression_result_checksum is not None:
                cachemanager.expression_to_checksum[expression] = \
                    expression_result_checksum
        
        return expression_result_checksum

from .get_buffer import GetBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .serialize_buffer import SerializeToBufferTask
from ..expression import Expression
from ...protocol.evaluate import needs_buffer_evaluation, evaluate_from_checksum, evaluate_from_buffer
from ...protocol.conversion import conversion_forbidden
from ...protocol.validate_subcelltype import validate_subcelltype
from ...protocol.expression import get_subpath
from .checksum import CalculateChecksumTask
