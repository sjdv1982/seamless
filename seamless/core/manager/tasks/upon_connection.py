import asyncio

from . import Task

class UponConnectionTask(Task):
    def __init__(self, manager, source, source_subpath, target, target_subpath):
        from ...worker import InputPin, OutputPin, EditPin
        self.source = source
        self.source_subpath = source_subpath
        self.target = target
        self.target_subpath = target_subpath
        self.current_macro = curr_macro()
        super().__init__(manager)
        if isinstance(source, (OutputPin, EditPin) ):
            self.dependencies.append(source.worker_ref())
        else:    
            self.dependencies.append(source)
        if isinstance(target, (InputPin, EditPin) ):
            self.dependencies.append(target.worker_ref())
        else:
            self.dependencies.append(target)

    def _connect_cell_cell(self):
        source, target, source_subpath, target_subpath = (
          self.source, self.target, self.source_subpath, self.target_subpath
        )
        livegraph = self.manager().livegraph
        if source_subpath is None and target_subpath is None:
            # simple cell-cell
            return livegraph.connect_cell_cell(self.current_macro, source, target)
        raise NotImplementedError # livegraph branch

    def _connect_pin_cell(self):
        source, target, source_subpath, target_subpath = (
          self.source, self.target, self.source_subpath, self.target_subpath
        )
        assert source_subpath is None
        assert isinstance(target, Cell), target

        livegraph = self.manager().livegraph
        if target_subpath is None:
            # simple pin-cell
            return livegraph.connect_pin_cell(self.current_macro, source, target)
        raise NotImplementedError # livegraph branch

    def _connect_cell_pin(self):
        source, target, source_subpath, target_subpath = (
          self.source, self.target, self.source_subpath, self.target_subpath
        )

        assert target_subpath is None

        livegraph = self.manager().livegraph
        if source_subpath is None:
            # simple cell-pin
            return livegraph.connect_cell_pin(self.current_macro, source, target)
        raise NotImplementedError # livegraph branch

    def _connect_cell(self):        
        if isinstance(self.target, Cell):
            return self._connect_cell_cell()
        elif isinstance(self.target, PinBase):
            return self._connect_cell_pin()
        elif isinstance(self.target, MacroPath):
            return self._connect_cell_macropath()
        else:
            raise NotImplementedError # livegraph branch

    def _connect_macropath(self):        
        assert isinstance(self.target, Cell) # if not, should have been caught earlier
        assert self.source_subpath is None
        if self.target_subpath is not None:
            raise NotImplementedError # livegraph branch ; will we ever support this?
        livegraph = self.manager().livegraph
        return livegraph.connect_macropath_cell(self.current_macro, self.source, self.target)

    async def _run(self):
        """Perform actions upon connection.

- Cancel any set-cell-value tasks on the target (if a cell)
- Await all other UponConnectionTasks
  Inform authoritymanager, caches etc., returning an accessor.
  This accessor will automatically be updated if anything modifies the source
  (even if it is already running, but not finished, now)
- Launch an accessor update task
"""
        manager = self.manager()
        taskmanager = manager.taskmanager

        target = self.target
        cancel_tasks = []
        if isinstance(target, Cell):
            for task in taskmanager.cell_to_task[target]:
                if isinstance(task, SetCellValueTask):
                    cancel_tasks.append(task)
        elif isinstance(target, PinBase):
            worker = target.worker_ref()
            if isinstance(worker, Transformer):
                cancel_tasks = taskmanager.transformer_to_task[worker]
            elif isinstance(worker, Reactor):
                cancel_tasks = taskmanager.reactor_to_task[worker]
            elif isinstance(worker, Macro):
                cancel_tasks = taskmanager.macro_to_task[worker]
            else:
                raise TypeError(type(worker))
        else:
            raise TypeError(type(target))
        for task in cancel_tasks:
            if isinstance(task, UponConnectionTask):
                continue
            task.cancel()

        await taskmanager.await_upon_connection_tasks(self.taskid)

        source = self.source
        if isinstance(source, Cell):
            accessor = self._connect_cell()
            assert accessor is not None
            if not source._void:
                CellUpdateTask(manager, source).launch()
        elif isinstance(source, PinBase):
            accessor = self._connect_pin_cell()
            assert accessor is not None
            worker = source.worker_ref()
            if isinstance(worker, Transformer):
                TransformerUpdateTask(manager, worker).launch()
            elif isinstance(worker, Reactor):
                ReactorUpdateTask(manager, worker).launch()
            elif isinstance(worker, Macro):
                MacroUpdateTask(manager, worker).launch()
            else:
                raise TypeError(type(worker))
        elif isinstance(source, MacroPath):
            accessor = self._connect_macropath()
            assert accessor is not None
            source2 = source._cell
            if source2 is not None:
                assert source in source2._paths
                if not source2._void:
                    CellUpdateTask(manager, source2).launch()
        else:
            raise TypeError(type(source))
    

from .cell_update import CellUpdateTask
from .transformer_update import TransformerUpdateTask
from .reactor_update import ReactorUpdateTask
from .macro_update import MacroUpdateTask
from .set_value import SetCellValueTask
from ...cell import Cell
from ...worker import PinBase
from ...transformer import Transformer
from ...reactor import Reactor
from ...macro import Macro, curr_macro, Path as MacroPath
