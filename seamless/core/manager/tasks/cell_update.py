from . import Task

class CellUpdateTask(Task):
    def __init__(self, manager, cell):
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
            - construct (not evaluate!) their expression using the cell checksum 
            Constructing a downstream expression increfs the cell checksum
            - launch an accessor update task
        """
        cell = self.cell
        if cell._void:
            print("WARNING: cell %s is void, shouldn't happen during cell update" % cell)
            return
        from . import SerializeToBufferTask, CellChecksumTask, CellUpdateTask
        manager = self.manager()
        cell = self.cell
        await CellChecksumTask(manager, cell).run()
        checksum, void = cell._checksum, cell._void
        if checksum is None and not void:
            manager.cancel_cell(cell, void=True)
        assert not cell._monitor # cell update is not for StructuredCell cells
        livegraph = manager.livegraph
        accessors = livegraph.cell_to_downstream[cell]
        for accessor in accessors:
            #- construct (not evaluate!) their expression using the cell checksum 
            #  Constructing a downstream expression increfs the cell checksum
            changed = accessor.build_expression(livegraph, checksum)
            #- launch an accessor update task
            if changed:
                AccessorUpdateTask(manager, accessor).launch()
        return None

from .accessor_update import AccessorUpdateTask        