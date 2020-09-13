from . import Task

class TransformerUpdateTask(Task):
    waiting_for_job = False
    def __init__(self, manager, transformer):
        self.transformer = transformer
        super().__init__(manager)
        self.dependencies.append(transformer)

    async def _run(self):
        transformer = self.transformer
        manager = self.manager()
        livegraph = manager.livegraph
        taskmanager = manager.taskmanager
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())
        assert not transformer._void, transformer
        upstreams = livegraph.transformer_to_upstream[transformer]
        downstreams = livegraph.transformer_to_downstream[transformer]
        inputpins = {}

        ok = True
        for pinname, accessor in upstreams.items():
            if accessor._checksum is None: #pending
                ok = False
                #print("TF PENDING", transformer, pinname)
                assert not accessor._void, (transformer, pinname)
        if not ok:
            return

        for pinname, accessor in upstreams.items():
            inputpins[pinname] = accessor._checksum

        first_output = downstreams[0].write_accessor.target()
        celltypes = {}
        for pinname, accessor in upstreams.items():
            wa = accessor.write_accessor
            celltypes[pinname] = wa.celltype, wa.subcelltype
        transformer._last_inputs = inputpins
        cachemanager = manager.cachemanager
        transformation_cache = cachemanager.transformation_cache
        outputname = transformer._output_name
        outputpin0 = transformer._pins[outputname]
        output_celltype = outputpin0.celltype
        output_subcelltype = outputpin0.subcelltype
        if output_celltype is None:
            output_celltype = first_output._celltype
            output_subcelltype = first_output._subcelltype
        outputpin = outputname, output_celltype, output_subcelltype
        self.waiting_for_job = True
        await transformation_cache.update_transformer(
            transformer, celltypes, inputpins, outputpin
        )
        return None

class TransformerResultUpdateTask(Task):
    def __init__(self, manager, transformer):
        self.transformer = transformer
        super().__init__(manager)
        self.dependencies.append(transformer)

    async def _run(self):
        transformer = self.transformer
        if transformer._void:
            print("WARNING: transformer %s is void, shouldn't happen during transformer update" % transformer)
            return
        manager = self.manager()
        livegraph = manager.livegraph
        accessors = livegraph.transformer_to_downstream[transformer]
        checksum = transformer._checksum
        preliminary = transformer.preliminary
        for accessor in accessors:
            #- construct (not compute!) their expression using the cell checksum
            #  Constructing a downstream expression increfs the cell checksum
            changed = accessor.build_expression(livegraph, checksum)
            if accessor._prelim != preliminary:
                accessor._prelim = preliminary
                changed = True
            #- launch an accessor update task
            if changed:
                AccessorUpdateTask(manager, accessor).launch()
        return None

from .accessor_update import AccessorUpdateTask
from ...status import StatusReasonEnum
from . import is_equal