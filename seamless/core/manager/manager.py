class Manager:
    _destroyed = False
    _active = True
    def __init__(self, ctx):
        ###from . import (ValueManager, StatusManager, AuthorityManager, 
        ### LiveGraph, JobManager)
        from .livegraph import LiveGraph
        from .cachemanager import CacheManager
        assert ctx._toplevel
        self.ctx = ctx
        from ... import communionserver
        ###communionserver.register_manager(self)
        self.livegraph = LiveGraph(self)
        self.cachemanager = CacheManager(self)

        # for now, just a single global mountmanager
        from ..mount import mountmanager
        self.mountmanager = mountmanager


    ##########################################################################
    # API section I: Registration (divide among subsystems)
    ##########################################################################

    def register_cell(self, cell):
        self.cachemanager.register_cell(cell)
        self.livegraph.register_cell(cell)

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


    def set_cell_checksum(self, cell, checksum, status=None):
        raise NotImplementedError # livegraph branch

    def set_cell(self, cell, value):
        assert self.livegraph.has_authority(cell)
        self._cancel_cell(cell, value is None)
        task = SetCellValueTask(self, cell, value)
        task.launch()

    ##########################################################################
    # API section ???: Cancellation
    ##########################################################################
    def _cancel_cell(self, cell, void):
        pass # TODO: livegraph branch

    ##########################################################################
    # API section ???: Destruction
    ##########################################################################

    def _destroy_cell(self, cell):
        self.cachemanager.destroy_cell(cell)
        self.livegraph.destroy_cell(cell)

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
