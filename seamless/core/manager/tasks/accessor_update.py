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
            manager.cancel_accessor(accessor, void=True, origin_task=self)
            return

        expression_result_checksum = await EvaluateExpressionTask(manager, expression).run()

        # If the expression result is None, do an accessor void cancellation
        if expression_result_checksum is None:
            manager.cancel_accessor(accessor, void=True, origin_task=self)
            return
        if accessor._checksum == expression_result_checksum:
            return
        accessor._checksum = expression_result_checksum
        accessor._void = False

        # Select the write accessor's target.
        target = accessor.write_accessor.target()
        if target is None:
            return
        
        if isinstance(target, Worker):
            # If a worker, set the pin to the checksum, and launch a worker update task.
            pinname = accessor.write_accessor.pinname
            manager.livegraph.set_pin(target, pinname, expression_result_checksum)
            WorkerUpdateTask(manager, target).launch()
        elif isinstance(target, Cell): # If a cell:
            if accessor.write_accessor.path is None:
                await manager.taskmanager.await_upon_connection_tasks()
                manager._set_cell_checksum(target, expression_result_checksum, False)
            else:
                # Run a set-non-authorative-path *action*, which will launch a set-path task.
                raise NotImplementedError #livegraph branch
            # Launch a cell update task (it will automatically await the set-path task, if any)
            CellUpdateTask(manager, target).launch()
        else:
            raise TypeError(target)
            
from ..accessor import ReadAccessor
from .evaluate_expression import EvaluateExpressionTask
from .worker_update import WorkerUpdateTask
from .cell_update import CellUpdateTask
from ...worker import Worker
from ...cell import Cell