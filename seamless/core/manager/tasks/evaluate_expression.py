from . import Task

class EvaluateExpressionTask(Task):
    @property
    def refkey(self):
        return self.expression

    def __init__(self, manager, expression):
        assert isinstance(expression, Expression)
        self.expression = expression
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
        expression_result_checksum = \
          cachemanager.expression_to_checksum.get(expression)
        if expression_result_checksum is None:
            # If the expression is trivial, obtain its result checksum directly
            if expression.path is None and not needs_buffer_evaluation(
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
                if expression.path is None:
                    expression_result_checksum = await evaluate_from_buffer(
                        expression.checksum, buffer, 
                        expression.celltype, expression.target_celltype,
                        buffer_cache
                    )
                else:
                    if (expression.celltype, expression.target_celltype) \
                        in conversion_forbidden:
                            raise TypeError
                    value = await DeserializeBufferTask(
                        manager, expression.checksum, buffer,
                        expression.celltype, copy=False
                    ).run()
                    # Special cases for cson / yaml
                    raise NotImplementedError #livegraph branch
                    # ...                  
                    # Apply path
                    # ...
                    raise NotImplementedError #livegraph branch
                    #result_value...
                    result_buffer = await SerializeToBufferTask(
                        manager, result_value, 
                        expression.target_celltype
                    ).run()
                    expression_result_checksum = await CalculateChecksumTask(
                        manager, buffer
                    ).run()
                await validate_subcelltype(
                    expression_result_checksum, 
                    expression.target_celltype, 
                    expression.target_subcelltype, 
                    expression.target_cell_path,
                    buffer_cache
                )                    
        else:
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
from .checksum import CalculateChecksumTask
