from . import Task

class CellUpdateTask(Task):
    def __init__(self, manager, cell):
        assert cell._structured_cell is None or cell._structured_cell.schema is cell, cell # cell update is not for StructuredCell cells, unless schema
        self.cell = cell
        super().__init__(manager)
        self._dependencies.append(cell)

    async def _run(self):
        """Updates the downstream dependencies (accessors) of a cell"""
        cell = self.cell
        if cell._void:
            print("WARNING: cell %s is void, shouldn't happen during cell update" % cell)
            return
        manager = self.manager()
        taskmanager = manager.taskmanager
        cell = self.cell

        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())
        await taskmanager.await_cell(cell, self.taskid, self._root())

        locknr = await acquire_evaluation_lock(self)
        try:
            checksum = cell._checksum
            assert not cell._structured_cell # cell update is not for StructuredCell cells
            livegraph = manager.livegraph
            accessors = livegraph.cell_to_downstream[cell]
            for path in cell._paths:
                path_accessors = livegraph.macropath_to_downstream[path]
                accessors = accessors + path_accessors
            for accessor in accessors:
                #- construct (not compute!) their expression using the cell checksum
                #  Constructing a downstream expression increfs the cell checksum
                changed = accessor.build_expression(livegraph, checksum)
                if cell._prelim != accessor._prelim:
                    accessor._prelim = cell._prelim
                    changed = True
                #- launch an accessor update task
                if changed or accessor._new_macropath:
                    task = AccessorUpdateTask(manager, accessor)
                    task.launch()
            for editpin in livegraph.cell_to_editpins[cell]:
                reactor = editpin.worker_ref()
                ReactorUpdateTask(manager, reactor).launch()
            sc = cell._structured_cell
            if sc is not None:
                if sc.schema is not cell:
                    print("WARNING: cell %s has a structured cell but is not its schema, shouldn't happen during cell update" % cell)
                buffer = await GetBufferTask(manager, checksum).run()
                value = await DeserializeBufferTask(
                    manager, buffer, checksum, cell.celltype, copy=True
                )
                manager.update_schema_cell(cell, value, None)
            return None
        finally:
            release_evaluation_lock(locknr)

from .accessor_update import AccessorUpdateTask
from .reactor_update import ReactorUpdateTask
from .get_buffer import GetBufferTask
from .deserialize_buffer import DeserializeBufferTask
from . import acquire_evaluation_lock, release_evaluation_lock