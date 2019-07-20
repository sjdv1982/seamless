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


    ##########################################################################
    # API section ???: Destruction
    ##########################################################################

    def _destroy_cell(self, cell):
        print("_destroy_cell", cell)
        self.cachemanager.destroy_cell(cell)

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
