from . import Task

class ReactorUpdateTask(Task):
    def __init__(self, manager, reactor):
        self.reactor = reactor
        super().__init__(manager)
        self.dependencies.append(reactor)

    async def _run(self):
        reactor = self.reactor
        if reactor._void:
            print("WARNING: reactor %s is void, shouldn't happen during reactor update" % reactor)
            return
        from . import SerializeToBufferTask
        manager = self.manager()
        livegraph = manager.livegraph
        raise NotImplementedError # livegraph branch
        # ...
        accessors = livegraph.reactor_to_downstream[reactor]
        for accessor in accessors:
            #- construct (not evaluate!) their expression using the cell checksum 
            #  Constructing a downstream expression increfs the cell checksum
            changed = accessor.build_expression(livegraph, checksum)
            #- launch an accessor update task
            if changed:
                AccessorUpdateTask(manager, accessor).launch()
        return None

from .accessor_update import AccessorUpdateTask        