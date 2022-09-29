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
            self._dependencies.append(source.worker_ref())
        elif isinstance(source, Cell):
            self._dependencies.append(source)
        elif isinstance(source, Path):
            self._dependencies.append(source)
        else:
            raise TypeError(source)
        if isinstance(target, (InputPin, EditPin) ):
            self._dependencies.append(target.worker_ref())
        elif isinstance(target, Cell):
            self._dependencies.append(target)
        elif isinstance(target, Path):
            self._dependencies.append(target)
        else:
            raise TypeError(target)


        taskmanager = manager.taskmanager
        cancel_tasks = []
        is_macro = False
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
                is_macro = True
            else:
                raise TypeError(type(worker))
        else:
            raise TypeError(type(target))
        if is_macro:
            manager.macromanager.cancel_macro(worker)
        else:
            for task in cancel_tasks:
                if isinstance(task, UponConnectionTask):
                    continue
                task.cancel()

        source = self.source
        target = self.target


    def _connect_cell_cell(self):
        source, target, source_subpath, target_subpath = (
          self.source, self.target, self.source_subpath, self.target_subpath
        )
        livegraph = self.manager().livegraph
        if source_subpath is None and target_subpath is None:
            # simple cell-cell
            return livegraph.connect_cell_cell(
                self.current_macro, source, target,
                from_upon_connection_task=self
            )
        elif source_subpath is not None and target_subpath is None:
            # outchannel-to-simple-cell
            return livegraph.connect_scell_cell(
                self.current_macro, source, source_subpath, target,
                from_upon_connection_task=self
            )
        elif source_subpath is None and target_subpath is not None:
            # simple-cell-to-inchannel
            return livegraph.connect_cell_scell(
                self.current_macro, source, target, target_subpath,
                from_upon_connection_task=self
            )
        else:
            # outchannel-to-inchannel
            return livegraph.connect_scell_scell(
                self.current_macro,
                source, source_subpath,
                target, target_subpath,
                from_upon_connection_task=self
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
            return livegraph.connect_pin_cell(
                self.current_macro, source, target,
                from_upon_connection_task=self
            )
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
        return livegraph.connect_cell_macropath(
            self.current_macro, self.source, self.target,
            from_upon_connection_task=self
        )

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
        return livegraph.connect_macropath_cell(
            self.current_macro, self.source, self.target,
            from_upon_connection_task=self
        )

    def _connect_editpin(self, pin, cell):
        assert isinstance(pin, EditPin)
        assert isinstance(cell, Cell)
        reactor = pin.worker_ref()
        manager = self.manager()
        livegraph = manager.livegraph
        rt_reactor = livegraph.rtreactors[reactor]
        is_void = reactor._void
        is_live = rt_reactor.live
        if is_live:
            rt_reactor.stop()
        assert livegraph.editpin_to_cell[reactor][pin.name] is None, (reactor, pin.name) # editpin can connect only to one cell
        livegraph.editpin_to_cell[reactor][pin.name] = cell
        livegraph.cell_to_editpins[cell].append(pin)
        livegraph.connect_pin_cell(
            self.current_macro, pin, cell,
            from_upon_connection_task=self
        )
        unvoid_reactor(reactor, livegraph)  # result connection may unvoid the reactor
        if is_live or (is_void and not reactor._void):
            manager.cancel_reactor(reactor,void=False)
            ReactorUpdateTask(manager, reactor).launch()

    async def _run(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager

        source = self.source
        target = self.target

        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())
        accessor = None

        if isinstance(source, Cell):
            if isinstance(target, EditPin):
                self._connect_editpin(target, source)
                return
            else:
                accessor = self._connect_cell()
                assert accessor is not None and isinstance(accessor, ReadAccessor), type(accessor)
        elif isinstance(source, EditPin):
            assert isinstance(target, (Cell, MacroPath))
            if isinstance(target, MacroPath):
                raise TypeError("Editpin '%s': illegal connection to macropath '%s'" % (source, target))
            self._connect_editpin(source, target)
        elif isinstance(source, PinBase):
            accessor = self._connect_pin_cell()
            assert accessor is not None and isinstance(accessor, ReadAccessor), type(accessor)
            source = source.worker_ref()
        elif isinstance(source, MacroPath):
            accessor = self._connect_macropath()
            assert accessor is not None and isinstance(accessor, ReadAccessor), type(accessor)
            source2 = source._cell
            if source2 is not None:
                assert source in source2._paths
            else:
                manager.cancel_accessor(accessor, True, origin_task=self, reason=StatusReasonEnum.UNCONNECTED)

                # Chance that the above line cancels our own task
                if self._canceled:
                    return

            source = source2
        else:
            raise TypeError(type(source))

        # Chance that the livegraph invocation cancels our own task
        if self._canceled:
            return


        if accessor is not None and source is not None:
            if isinstance(source, Cell):
                if not source._void:
                    taskmanager = manager.taskmanager
                    unvoid_accessor(accessor, manager.livegraph)
                    manager.cancel_accessor(accessor, void=False, origin_task=self)

                    # Chance that the above lines cancels our own task
                    if self._canceled:
                        return

                    accessor.build_expression(manager.livegraph, source._checksum)
                    if source._checksum is not None:
                        AccessorUpdateTask(manager, accessor).launch()

            elif isinstance(source, Transformer):
                if source._void:
                    unvoid_transformer(source, manager.livegraph)  # result connection may unvoid the transformer, which will launch a task

                    # Chance that the above lines cancels our own task
                    if self._canceled:
                        return

                else:
                    unvoid_accessor(accessor, manager.livegraph)

                    # Chance that the above lines cancels our own task
                    if self._canceled:
                        return

                    if source._checksum is not None:
                        TransformerUpdateTask(manager, source).launch()
            elif isinstance(source, Reactor):
                if source._void:
                    unvoid_reactor(source, manager.livegraph)  # result connection may unvoid the reactor, which will launch a task

                    # Chance that the above lines cancels our own task
                    if self._canceled:
                        return

                else:
                    unvoid_accessor(accessor, manager.livegraph)

                    # Chance that the above lines cancels our own task
                    if self._canceled:
                        return

                    if source._checksum is not None:
                        manager.cancel_reactor(reactor,void=False)
                        ReactorUpdateTask(manager, source).launch()
            else:
                raise TypeError(source)

        #print("/UPON")

class UponBiLinkTask(UponConnectionTask):
    def __init__(self, manager, source, target):
        self.source = source
        self.target = target
        self.current_macro = curr_macro()
        Task.__init__(self, manager)
        if not isinstance(source, Cell):
            raise TypeError(type(source))
        if not isinstance(target, (Cell, MacroPath)):
            raise TypeError(type(target))
        self._dependencies.append(source)
        self._dependencies.append(target)

    async def _run(self):
        if self.target is None:
            return
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager

        source = self.source
        target = self.target

        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())

        livegraph = self.manager().livegraph
        livegraph.bilink(
            self.current_macro, source, target
        )



from .cell_update import CellUpdateTask
from .accessor_update import AccessorUpdateTask
from .transformer_update import TransformerUpdateTask
from .reactor_update import ReactorUpdateTask
from .set_value import SetCellValueTask
from ..accessor import ReadAccessor
from ...cell import Cell
from ...structured_cell import Inchannel
from ...worker import PinBase, EditPin
from ...transformer import Transformer
from ...reactor import Reactor
from ...macro_mode import curr_macro
from ...macro import Macro, Path as MacroPath
from ...status import StatusReasonEnum
from ..unvoid import unvoid_accessor, unvoid_transformer, unvoid_reactor