from . import Task

class CellUpdateTask(Task):
    def __init__(self, manager, cell, *, origin_reactor=None):
        assert cell._structured_cell is None or cell._structured_cell.schema is cell, cell # cell update is not for StructuredCell cells, unless schema
        self.cell = cell
        self.origin_reactor = origin_reactor
        super().__init__(manager)
        self._dependencies.append(cell)

        # assertion
        livegraph = manager.livegraph
        accessors = livegraph.cell_to_downstream[cell]
        for path in cell._paths:
            path_accessors = livegraph.macropath_to_downstream[path]
            accessors = accessors + path_accessors
        for accessor in accessors:
            target = accessor.write_accessor.target()
            if isinstance(target, MacroPath):
                target = target._cell
                if target is None:
                    continue
            if isinstance(target, Cell):
                assert not target._void, accessor
        #

    async def _run(self):
        """Updates the downstream dependencies (accessors) of a cell"""
        cell = self.cell
        if cell._void:
            print("WARNING: cell %s is void, shouldn't happen during cell update" % cell)
            return
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager
        cell = self.cell

        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())
        await taskmanager.await_cell(cell, self.taskid, self._root())

        fallback = manager.get_fallback(cell)

        locknr = await acquire_evaluation_lock(self)
        try:
            if fallback is not None:
                checksum = fallback._checksum
            else:
                checksum = cell._checksum
            assert checksum is not None, cell
            assert not cell._structured_cell # cell update is not for StructuredCell cells
            livegraph = manager.livegraph
            accessors = livegraph.cell_to_downstream[cell]
            for path in cell._paths:
                path_accessors = livegraph.macropath_to_downstream[path]
                accessors = accessors + path_accessors

            accessors_to_cancel = []

            for accessor in accessors:
                if accessor._void or accessor._checksum is not None:
                    accessors_to_cancel.append(accessor)
                else:
                    manager.taskmanager.cancel_accessor(accessor)

            manager.cancel_accessors(accessors_to_cancel, False)

            # Chance that the above line cancels our own task
            if self._canceled:
                return

            for accessor in accessors:
                #- launch an accessor update task
                target = accessor.write_accessor.target()
                if isinstance(target, MacroPath):
                    target = target._cell
                    if target is None:
                        continue
                if isinstance(target, Cell):
                    assert not target._void, accessor

                accessor.build_expression(livegraph, checksum)
                task = AccessorUpdateTask(manager, accessor)
                task.launch()
            for editpin in livegraph.cell_to_editpins[cell]:
                reactor = editpin.worker_ref()
                if reactor is not self.origin_reactor:
                    if not reactor._void:
                        ReactorUpdateTask(manager, reactor).launch()
            if cell in livegraph.cell_to_macro_elision:
                for elision in livegraph.cell_to_macro_elision[cell]:
                    macro = elision.macro
                    if macro._in_elision:
                        MacroUpdateTask(manager, macro).launch()

            manager.trigger_all_fallbacks(cell)
            return None
        finally:
            release_evaluation_lock(locknr)

from .accessor_update import AccessorUpdateTask
from .reactor_update import ReactorUpdateTask
from .get_buffer import GetBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .macro_update import MacroUpdateTask
from . import acquire_evaluation_lock, release_evaluation_lock
from ...macro import Path as MacroPath
from ...cell import Cell