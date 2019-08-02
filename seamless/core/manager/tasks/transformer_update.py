from . import Task

def is_equal(old, new):
    if new is None:
        return False
    if len(old) != len(new):
        return False
    for k in old:
        if old[k] != new[k]:
            return False
    return True

class TransformerUpdateTask(Task):
    def __init__(self, manager, transformer):
        self.transformer = transformer
        super().__init__(manager)
        self.dependencies.append(transformer)

    async def _run(self):
        transformer = self.transformer
        from . import SerializeToBufferTask
        manager = self.manager()
        livegraph = manager.livegraph
        upstreams = livegraph.transformer_to_upstream[transformer]
        inputpins = {}
        for pinname, accessor in upstreams.items():
            if accessor is None: #unconnected
                transformer._status_reason = StatusReasonEnum.UNCONNECTED
                return
                
        status_reason = None        
        for pinname, accessor in upstreams.items():
            if accessor._void: #undefined/upstream error
                reason = accessor._status_reason
            elif accessor._checksum is None:
                reason = StatusReasonEnum.UNDEFINED
            else:
                continue
            if status_reason is None or reason < status_reason:
                status_reason = reason
        self._status_reason = status_reason

        if status_reason is not None:
            return

        for pinname, accessor in upstreams.items():
            inputpins[pinname] = accessor._checksum
        if is_equal(inputpins, transformer._last_inputs):
            return
        downstreams = livegraph.transformer_to_downstream[transformer]
        if not len(downstreams):
            return
        first_output = downstreams[0].write_accessor.target()
        celltypes = {}
        for pinname, accessor in upstreams.items():
            wa = accessor.write_accessor
            celltypes[pinname] = wa.celltype, wa.subcelltype
        transformer._last_inputs = inputpins
        cachemanager = manager.cachemanager
        transformation_cache = cachemanager.transformation_cache
        buffer_cache = cachemanager.buffer_cache
        outputname = transformer._output_name
        outputpin0 = transformer._pins[outputname]
        output_celltype = outputpin0.celltype
        output_subcelltype = outputpin0.subcelltype
        if output_celltype is None:
            output_celltype = first_output._celltype
            output_subcelltype = first_output._subcelltype
        outputpin = outputname, output_celltype, output_subcelltype
        #print("TRANSFORM!", transformer)
        await transformation_cache.update_transformer(
            transformer, celltypes, inputpins, outputpin, buffer_cache
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
        for accessor in accessors:
            #- construct (not evaluate!) their expression using the cell checksum 
            #  Constructing a downstream expression increfs the cell checksum
            changed = accessor.build_expression(livegraph, checksum)
            #- launch an accessor update task
            if changed:
                AccessorUpdateTask(manager, accessor).launch()
        return None

from .accessor_update import AccessorUpdateTask
from ...status import StatusReasonEnum