from . import Task

class AccessorUpdateTask(Task):
    def __init__(self, manager, accessor):
        assert isinstance(accessor, ReadAccessor)
        self.accessor = accessor
        super().__init__(manager)
        self.dependencies.append(accessor)

    async def _run(self):
        accessor = self.accessor        
        # Get the expression. If it is None, do an accessor void cancellation
        expression = accessor.expression        
        manager = self.manager()
        
        if expression is None:
            accessor._status_reason = StatusReasonEnum.UNDEFINED
            manager.cancel_accessor(accessor, void=True, origin_task=self)
            return        

        expression_result_checksum = await EvaluateExpressionTask(manager, expression).run()

        # If the expression result is None, do an accessor void cancellation
        if expression_result_checksum is None:
            accessor._status_reason = StatusReasonEnum.INVALID
            manager.cancel_accessor(accessor, void=True, origin_task=self)
            return
        if accessor._checksum == expression_result_checksum:
            if not accessor._new_macropath:
                return
        accessor._checksum = expression_result_checksum
        accessor._void = False
        accessor._status_reason = None

        # Select the write accessor's target.
        target = accessor.write_accessor.target()
        if isinstance(target, MacroPath):            
            target = target._cell
        if target is None:
            return
        
        accessor._new_macropath = False
        if isinstance(target, Worker):
            worker = target
            # If a worker, launch a worker update task. The worker will retrieve the upstream checksums by itself.
            if isinstance(worker, Transformer):
                TransformerUpdateTask(manager, worker).launch()
            elif isinstance(worker, Reactor):
                ReactorUpdateTask(manager, worker).launch()
            elif isinstance(worker, Macro):
                MacroUpdateTask(manager, worker).launch()
            else:
                raise TypeError(type(worker))
        elif isinstance(target, Cell): # If a cell:
            if accessor.write_accessor.path is None:
                await manager.taskmanager.await_upon_connection_tasks(self.taskid)
                manager._set_cell_checksum(
                    target, expression_result_checksum, 
                    False, None, prelim=accessor._prelim
                )
            else:
                # Run a set-non-authorative-path *action*, which will launch a set-path task.
                raise NotImplementedError #livegraph branch
            # Launch a cell update task (it will automatically await the set-path task, if any)
            CellUpdateTask(manager, target).launch()
        else:
            raise TypeError(target)
            
from ..accessor import ReadAccessor
from .evaluate_expression import EvaluateExpressionTask
from .transformer_update import TransformerUpdateTask
from .reactor_update import ReactorUpdateTask
from .macro_update import MacroUpdateTask
from .cell_update import CellUpdateTask
from ...worker import Worker
from ...transformer import Transformer
from ...reactor import Reactor
from ...macro import Macro, Path as MacroPath
from ...cell import Cell
from ...status import StatusReasonEnum