import asyncio

from . import Task

class UponConnectionTask(Task):
    def __init__(self, manager, source, source_subpath, target, target_subpath):
        from ...worker import InputPin, OutputPin, EditPin
        from ...macro import Path
        self.source = source
        self.source_subpath = source_subpath
        self.target = target
        self.target_subpath = target_subpath
        self.current_macro = curr_macro()
        super().__init__(manager)
        if isinstance(source, (OutputPin, EditPin) ):
            self.dependencies.append(source.worker_ref())                    
        elif isinstance(source, Cell):
            self.dependencies.append(source)
        elif isinstance(source, Path):
            self.dependencies.append(source)
        else:
            raise TypeError(source)
        if isinstance(target, (InputPin, EditPin) ):
            self.dependencies.append(target.worker_ref())        
        elif isinstance(target, Cell):
            self.dependencies.append(target)
        elif isinstance(target, Path):
            self.dependencies.append(source)
        else:
            raise TypeError(target)

    def _connect_cell_cell(self):
        source, target, source_subpath, target_subpath = (
          self.source, self.target, self.source_subpath, self.target_subpath
        )
        livegraph = self.manager().livegraph
        if source_subpath is None and target_subpath is None:
            # simple cell-cell
            return livegraph.connect_cell_cell(
                self.current_macro, source, target
            )
        elif source_subpath is not None and target_subpath is None:
            # outchannel-to-simple-cell
            return livegraph.connect_scell_cell(
                self.current_macro, source, source_subpath, target
            )
        elif source_subpath is None and target_subpath is not None:
            # simple-cell-to-inchannel
            return livegraph.connect_cell_scell(
                self.current_macro, source, target, target_subpath
            )
        else:
            # outchannel-to-inchannel
            return livegraph.connect_scell_scell(
                self.current_macro, 
                source, source_subpath, 
                target, target_subpath
            )
            

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
        else:
            msg = """Pins cannot be connected directly to structured cells
Use a simple cell as an intermediate
Source %s; target %s, %s""" % (source, target, target_subpath)
            raise TypeError(msg)

    def _connect_cell_pin(self):
        source, target, source_subpath, target_subpath = (
          self.source, self.target, self.source_subpath, self.target_subpath
        )

        assert target_subpath is None

        livegraph = self.manager().livegraph
        if source_subpath is None:
            if isinstance(target, EditPin):
                return
            # simple cell-pin
            return livegraph.connect_cell_pin(self.current_macro, source, target)
        else:
            msg = """Pins cannot be connected directly from structured cells
Use a simple cell as an intermediate
Source %s, %s; target %s""" % (source._structured_cell, source_subpath, target)
            raise TypeError(msg)

    def _connect_cell_macropath(self):        
        source, target, source_subpath, target_subpath = (
          self.source, self.target, self.source_subpath, self.target_subpath
        )
        assert target_subpath is None
        if source_subpath is not None:
            msg = """Macro paths cannot be connected directly from structured cells
Use a simple cell as an intermediate
Source %s, %s; target %s""" % (source, source_subpath, target)
            raise TypeError(msg)
        livegraph = self.manager().livegraph
        return livegraph.connect_cell_macropath(self.current_macro, self.source, self.target)

    def _connect_cell(self):        
        if isinstance(self.target, Cell):
            return self._connect_cell_cell()
        elif isinstance(self.target, PinBase):
            return self._connect_cell_pin()
        elif isinstance(self.target, MacroPath):
            return self._connect_cell_macropath()
        else:
            msg = "Cannot connect cell to %s(%s)"
            raise TypeError(msg % (self.target, type(self.target)))

    def _connect_macropath(self):
        source, target, source_subpath, target_subpath = (
          self.source, self.target, self.source_subpath, self.target_subpath
        )
        assert isinstance(target, Cell) # if not, should have been caught earlier
        assert source_subpath is None
        if target_subpath is not None:
            msg = """Macro paths cannot be connected directly to a structured cells
Use a simple cell as an intermediate
Source %s; target %s, %s""" % (source, target, target_subpath)
        livegraph = self.manager().livegraph
        return livegraph.connect_macropath_cell(self.current_macro, self.source, self.target)

    def _connect_editpin(self, pin, cell):
        assert isinstance(pin, EditPin)
        assert isinstance(cell, Cell)
        reactor = pin.worker_ref()
        assert reactor._void # safe assumption, as long as must_be_defined is enforced to be True        
        manager = self.manager()
        livegraph = manager.livegraph
        assert livegraph.editpin_to_cell[reactor][pin.name] is None, (reactor, pin.name) # editpin can connect only to one cell
        livegraph.editpin_to_cell[reactor][pin.name] = cell
        livegraph.cell_to_editpins[cell].append(pin)
        ReactorUpdateTask(manager, reactor).launch()

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
        elif isinstance(target, MacroPath):
            cancel_tasks = taskmanager.macropath_to_task[target]
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
            if isinstance(target, EditPin):
                return self._connect_editpin(target, source)
            assert accessor is not None
            if not source._void:
                sc = source._structured_cell
                if sc is not None:
                    # TODO: not the most efficient...
                    assert sc._data is source, (sc._data, source)
                    sc._new_connections = True
                    manager.structured_cell_join(sc)
                else:
                    CellUpdateTask(manager, source).launch()
        elif isinstance(source, EditPin):
            assert isinstance(target, (Cell, MacroPath))
            return self._connect_editpin(source, target)
        elif isinstance(source, PinBase):
            accessor = self._connect_pin_cell()
            assert accessor is not None
            worker = source.worker_ref()
            if isinstance(worker, Transformer):
                TransformerUpdateTask(manager, worker).launch()
            elif isinstance(worker, Reactor):
                reactor = worker
                last_outputs = reactor._last_outputs
                checksum = None
                if last_outputs is not None:
                    checksum = last_outputs.get(pinname)
                if checksum is not None:
                    downstreams = livegraph.reactor_to_downstream[reactor][pinname]
                    for accessor in downstreams:
                        #- construct (not evaluate!) their expression using the cell checksum 
                        #  Constructing a downstream expression increfs the cell checksum
                        changed = accessor.build_expression(livegraph, checksum)
                        # TODO: prelim? tricky for a reactor...
                        #- launch an accessor update task
                        if changed:
                            AccessorUpdateTask(manager, accessor).launch()
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
from .accessor_update import AccessorUpdateTask
from .transformer_update import TransformerUpdateTask
from .reactor_update import ReactorUpdateTask
from .macro_update import MacroUpdateTask
from .set_value import SetCellValueTask
from ...cell import Cell
from ...worker import PinBase, EditPin
from ...transformer import Transformer
from ...reactor import Reactor
from ...macro_mode import curr_macro
from ...macro import Macro, Path as MacroPath
