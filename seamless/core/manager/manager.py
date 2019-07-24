class Manager:
    _destroyed = False
    _active = True
    def __init__(self, ctx):
        from .livegraph import LiveGraph
        from .cachemanager import CacheManager
        from .taskmanager import TaskManager
        assert ctx._toplevel
        self.ctx = ctx
        from ... import communionserver
        ###communionserver.register_manager(self)
        self.livegraph = LiveGraph(self)
        self.cachemanager = CacheManager(self)
        self.taskmanager = TaskManager(self)

        # for now, just a single global mountmanager
        from ..mount import mountmanager
        self.mountmanager = mountmanager


    ##########################################################################
    # API section I: Registration (divide among subsystems)
    ##########################################################################

    def register_cell(self, cell):
        self.cachemanager.register_cell(cell)
        self.livegraph.register_cell(cell)
        self.taskmanager.register_cell(cell)

    def register_structured_cell(self, structured_cell):
        self.livegraph.register_structured_cell(structured_cell)

    ##########################################################################
    # API section II: Actions
    ##########################################################################

    def connect_cell(self, cell, other, cell_subpath):
        #print("connect_cell", cell, other, cell_subpath)
        raise NotImplementedError # livegraph branch

    def connect_pin(self, pin, cell):
        raise NotImplementedError # livegraph branch


    def set_cell_checksum(self, cell, checksum, initial, is_buffercell):
        """Setting a cell checksum.
  (This is done from the command line, usually at graph loading)
  initial=True in case of graph loading; is_buffercell=True when triggered from StructuredCell)
  If "initial" is True, it is assumed that the context is being initialized (e.g. when created from a graph).
  Else, cell cannot be the .data or .buffer attribute of a StructuredCell, and cannot have any incoming connection.
  
  However, if "is_buffercell" is True, then the cell can be a .buffer attribute of a StructuredCell

  If the new checksum is None, do a cell void cancellation.  
  Else: 
    If old checksum is not None, do a cell cancellation.
    Set the cell as being non-void, set the checksum (direct attribute access), and launch a cell update task. 

        """
        sc_data = self.livegraph.datacells.get(cell) 
        sc_buf = self.livegraph.buffercells.get(cell)
        if not initial:
            assert sc_data is None
            if is_buffercell:
                if sc_buf is None:
                    raise Exception("Cell was declared to be buffercell, but it is not known as such")                
            else:
                assert self.livegraph.has_authority(cell)
                assert sc_buf is None
        if checksum is None:
            self.cancel_cell(cell, void=True)
        else:
            old_checksum = self.get_cell_checksum(cell)
            if old_checksum is not None:
                self.cancel_cell(cell, void=False)
        self._set_cell_checksum(cell, checksum, (checksum is None))

    def _set_cell_checksum(self, cell, checksum, void):
        # NOTE: any cell task depending on the old checksum must have been canceled already!
        assert checksum is None or isinstance(checksum, bytes), checksum
        assert isinstance(void, bool), void
        cell._checksum = checksum
        cell._void = void

    def set_cell(self, cell, value):
        assert self.livegraph.has_authority(cell)
        self.cancel_cell(cell, value is None)
        task = SetCellValueTask(self, cell, value)
        task.launch()

    def get_cell_checksum(self, cell):
        task = CellChecksumTask(self, cell)
        task.launch_and_await()
        return cell._checksum

    def get_cell_void(self, cell):
        task = CellChecksumTask(self, cell)
        task.launch_and_await()
        return cell._void

    def _get_buffer(self, checksum):
        if checksum is None:
            return None
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            return buffer
        return GetBufferTask(self, checksum).launch_and_await()

    def get_cell_buffer(self, cell):
        checksum = self.get_cell_checksum(cell)
        return self._get_buffer(checksum)
        
    def get_cell_value(self, cell, copy):
        checksum = self.get_cell_checksum(cell)
        if checksum is None:
            return None
        buffer = self._get_buffer(checksum)
        celltype = cell._celltype            
        task = DeserializeBufferTask(self, buffer, checksum, celltype, copy)
        value = task.launch_and_await()
        return value

    ##########################################################################
    # API section ???: Cancellation
    ##########################################################################
    def cancel_cell(self, cell, void, origin_task=None):
        """Cancels all tasks depending on cell, and sets all dependencies to None. 
If void=True, all dependencies are set to void as well.
If origin_task is provided, that task is not cancelled."""
        self.taskmanager.cancel_cell(cell, origin_task=origin_task)
        if cell._checksum is None:
            if not void or cell._void:
                return
        livegraph = self.livegraph
        accessors = livegraph.cell_to_downstream[cell]
        for accessor in accessors:            
            self.cancel_accessor(accessor, void)
        self._set_cell_checksum(cell, None, void)

    def cancel_accessor(self, accessor, void):
        raise NotImplementedError #livegraph branch

    ##########################################################################
    # API section ???: Destruction
    ##########################################################################

    def _destroy_cell(self, cell):
        self.cachemanager.destroy_cell(cell)
        self.livegraph.destroy_cell(cell)
        self.taskmanager.destroy_cell(cell)

    def destroy(self, from_del=False):
        if self._destroyed:
            return
        self._destroyed = True
        ###self.temprefmanager_future.cancel()
        ###self.flush_future.cancel()
        self.ctx._unmount(from_del=from_del, manager=self)
        self.ctx.destroy()

    def __del__(self):
        self.destroy(from_del=True)

from .tasks import (SetCellValueTask, CellChecksumTask, GetBufferTask,
  DeserializeBufferTask)

from ..protocol.calculate_checksum import checksum_cache
