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


    def set_cell_checksum(self, cell, checksum):
        raise NotImplementedError # livegraph branch

    def _set_cell_checksum(self, cell, checksum, void):
        cell._checksum = checksum
        cell._void = void

    def set_cell(self, cell, value):
        assert self.livegraph.has_authority(cell)
        self.cancel_cell(cell, value is None)
        task = SetCellValueTask(self, cell, value)
        task.launch()

    ##########################################################################
    # API section ???: Cancellation
    ##########################################################################
    def cancel_cell(self, cell, void):
        print("# TODO: livegraph branch, manager.cancel_cell")

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

from .tasks import SetCellValueTask