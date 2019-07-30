from . import Task

class MacroUpdateTask(Task):
    def __init__(self, manager, macro):
        self.macro = macro
        super().__init__(manager)
        self.dependencies.append(macro)

    async def _run(self):
        macro = self.macro
        if macro._void:
            print("WARNING: macro %s is void, shouldn't happen during macro update" % macro)
            return
        from . import SerializeToBufferTask
        manager = self.manager()
        livegraph = manager.livegraph
        raise NotImplementedError # livegraph branch
        # ...
        accessors = livegraph.macro_to_downstream[macro]
        for accessor in accessors:
            #- construct (not evaluate!) their expression using the cell checksum 
            #  Constructing a downstream expression increfs the cell checksum
            changed = accessor.build_expression(livegraph, checksum)
            #- launch an accessor update task
            if changed:
                AccessorUpdateTask(manager, accessor).launch()
        return None

from .accessor_update import AccessorUpdateTask        