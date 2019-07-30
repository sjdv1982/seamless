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
        if transformer._void:
            print("WARNING: transformer %s is void, shouldn't happen during transformer update" % transformer)
            return
        from . import SerializeToBufferTask
        manager = self.manager()
        livegraph = manager.livegraph
        upstreams = livegraph.transformer_to_upstream[transformer]
        inputpins = {}
        for pinname, accessor in upstreams.items():
            if accessor is None: #unconnected
                continue
            if accessor._void: #undefined/upstream error
                continue
            if accessor._checksum is None: #undefined
                continue
            inputpins[pinname] = accessor._checksum
        if len(inputpins) != len(upstreams):
            return
        if is_equal(inputpins, transformer._last_inputs):
            return
        print("TRANSFORM!", transformer, inputpins)
        transformer._last_inputs = inputpins
        raise NotImplementedError # livegraph branch
        # ...
        accessors = livegraph.transformer_to_downstream[transformer]
        for accessor in accessors:
            #- construct (not evaluate!) their expression using the cell checksum 
            #  Constructing a downstream expression increfs the cell checksum
            changed = accessor.build_expression(livegraph, checksum)
            #- launch an accessor update task
            if changed:
                AccessorUpdateTask(manager, accessor).launch()
        return None

from .accessor_update import AccessorUpdateTask        