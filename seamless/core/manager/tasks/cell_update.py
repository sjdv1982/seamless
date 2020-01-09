from . import Task

class CellUpdateTask(Task):
    def __init__(self, manager, cell):
        assert not cell._structured_cell, cell # cell update is not for StructuredCell cells
        self.cell = cell
        super().__init__(manager)
        self.dependencies.append(cell)

    async def _run(self):
        """
        - If the cell's void attribute is True, log a warning and return.
        - Await cell checksum task
        - If the checksum is None, for each output accessor:
            - do a void cancellation
          Else, for each output read accessor:
            - construct (not compute!) their expression using the cell checksum 
            Constructing a downstream expression increfs the cell checksum
            - launch an accessor update task
        """
        cell = self.cell
        if cell._void:
            print("WARNING: cell %s is void, shouldn't happen during cell update" % cell)
            return
        from . import CellChecksumTask
        manager = self.manager()
        cell = self.cell
        await CellChecksumTask(manager, cell).run()
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

from .accessor_update import AccessorUpdateTask
from .reactor_update import ReactorUpdateTask
from .get_buffer import GetBufferTask
from .deserialize_buffer import DeserializeBufferTask