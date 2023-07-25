from . import Task

class AccessorUpdateTask(Task):
    def __init__(self, manager, accessor):
        assert isinstance(accessor, ReadAccessor)

        expression = accessor.expression
        assert expression is not None, accessor

        self.accessor = accessor
        super().__init__(manager)
        self._dependencies.append(accessor)

        # assertion
        target = accessor.write_accessor.target()
        if isinstance(target, MacroPath):
            target = target._cell
            if target is None:
                return
        if isinstance(target, Cell):
            assert not target._void, accessor
        #

    async def _run(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())

        accessor = self.accessor

        expression = accessor.expression
        assert expression is not None, accessor

        livegraph = manager.livegraph
        assert expression in livegraph.expression_to_accessors

        assert not accessor._void
        path = accessor.write_accessor.path
        target = accessor.write_accessor.target()
        # assertion
        if not isinstance(target, MacroPath):
            if isinstance(target, Cell):
                cell = target
                if path is None:
                    assert not cell._void, cell
                    if not cell._prelim:
                        assert cell._checksum is None, cell
                else:
                    sc = target._structured_cell
                    try:
                        assert not target._void, (sc, cell, path)
                        inchannel = sc.inchannels[path]
                        assert not inchannel._void, (sc, cell, path)
                        if not sc._cyclic:
                            assert inchannel._checksum is None, (sc, cell, path)
                    except:
                        import traceback; traceback.print_exc()
                        return
        #

        try:
            expression_result_checksum = await evaluate_expression(expression, manager=manager)
        except Exception as exc:
            expression_result_checksum = None
            expression.exception = exc

        if expression_result_checksum is None:
            if expression.exception is None:
                reason = StatusReasonEnum.UPSTREAM
                accessor.exception = None
            else:
                reason = StatusReasonEnum.INVALID
                accessor.exception = expression.exception                
            manager.cancel_accessor(accessor, void=True, origin_task=self, reason=reason)

            target = accessor.write_accessor.target()
            if isinstance(target, MacroPath):
                target = target._cell
            if isinstance(target, Cell):
                livegraph.cell_parsing_exceptions[target] = expression.exception
                if target._in_structured_cell:
                    target = target._structured_cell
                    target._exception = expression.exception
            return
        else:
            accessor.exception = None
            target = accessor.write_accessor.target()
            if isinstance(target, MacroPath):
                target = target._cell
            if isinstance(target, Cell):
                livegraph.cell_parsing_exceptions[target] = None
                if target._in_structured_cell:
                    target = target._structured_cell
                    target._exception = None
        accessor._checksum = expression_result_checksum

        # Select the write accessor's target.
        target = accessor.write_accessor.target()
        if isinstance(target, MacroPath):
            target = target._cell
        if target is None:
            return

        locknr = await acquire_evaluation_lock(self)
        try:
            accessor._new_macropath = False
            if isinstance(target, Worker):
                worker = target
                # If a worker, launch a worker update task. The worker will retrieve the upstream checksums by itself.
                if isinstance(worker, Transformer):
                    manager.taskmanager.cancel_transformer(worker)
                    if not worker._void:
                        TransformerUpdateTask(manager, worker).launch()
                elif isinstance(worker, Reactor):
                    manager.taskmanager.cancel_reactor(worker)
                    if not worker._void:
                        manager.taskmanager.cancel_reactor(worker)
                        ReactorUpdateTask(manager, worker).launch()
                elif isinstance(worker, Macro):
                    manager.macromanager.cancel_macro(worker)
                    if not worker._void:
                        manager.macromanager.update_macro(worker)
                else:
                    raise TypeError(type(worker))
            elif isinstance(target, Cell): # If a cell:
                result_checksum = expression_result_checksum

                if path is None:
                    await manager.taskmanager.await_upon_connection_tasks(self.taskid, target._root())
                    manager._set_cell_checksum(
                        target, result_checksum,
                        False, None, prelim=accessor._prelim
                    )
                    if result_checksum is not None:
                        CellUpdateTask(manager, target).launch()
                else:
                    if not target._destroyed:
                        assert expression.target_celltype == "mixed", expression.target_celltype
                        sc = target._structured_cell
                        assert sc is not None
                        inchannel = sc.inchannels[path]

                        assert not inchannel._void, (sc, path)

                        manager._set_inchannel_checksum(
                            inchannel, result_checksum,
                            False, None, prelim=accessor._prelim
                        )
            else:
                raise TypeError(target)
        finally:
            release_evaluation_lock(locknr)

from ..accessor import ReadAccessor
from .evaluate_expression import evaluate_expression
from .transformer_update import TransformerUpdateTask
from .reactor_update import ReactorUpdateTask
from .cell_update import CellUpdateTask
from ...worker import Worker
from ...transformer import Transformer
from ...reactor import Reactor
from ...macro import Macro, Path as MacroPath
from ...cell import Cell
from ...status import StatusReasonEnum
from . import acquire_evaluation_lock, release_evaluation_lock
from ...macro import Path as MacroPath