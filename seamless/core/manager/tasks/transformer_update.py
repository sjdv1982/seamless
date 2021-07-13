from . import Task

import logging
logger = logging.getLogger("seamless")

def print_info(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)

def print_warning(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)

def print_debug(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)

def print_error(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)

class TransformerUpdateTask(Task):
    waiting_for_job = False
    def __init__(self, manager, transformer):
        self.transformer = transformer
        super().__init__(manager)
        self._dependencies.append(transformer)

    async def _run(self):
        transformer = self.transformer
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        livegraph = manager.livegraph
        taskmanager = manager.taskmanager
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())

        if transformer._void:
            print("WARNING: transformer %s is void, shouldn't happen during transformer update" % transformer)
            manager.cancel_transformer(transformer, True, StatusReasonEnum.ERROR)
            return

        upstreams = livegraph.transformer_to_upstream[transformer]
        downstreams = livegraph.transformer_to_downstream[transformer]

        status_reason = None
        for pinname, accessor in upstreams.items():
            if pinname == "META":
                continue
            if accessor is None: #unconnected
                status_reason = StatusReasonEnum.UNCONNECTED
                break
        else:
            for pinname, accessor in upstreams.items():
                if pinname == "META" and accessor is None:
                    continue
                if accessor._void: #upstream error
                    status_reason = StatusReasonEnum.UPSTREAM
        if not len(downstreams):
            status_reason = StatusReasonEnum.UNCONNECTED

        if status_reason is not None:
            print("WARNING: transformer %s is void, shouldn't happen during transformer update" % transformer)
            manager.cancel_transformer(transformer, True, status_reason)
            return

        for pinname, accessor in upstreams.items():
            if pinname == "META" and accessor is None:
                continue
            if accessor._checksum is None: #pending; a legitimate use case, but we can't proceed
                print_debug("ABORT", self.__class__.__name__, hex(id(self)), self.dependencies, " <= pinname", pinname)
                manager.cancel_transformer(transformer, False)
                return

        inputpins = {}
        for pinname, accessor in upstreams.items():
            if pinname == "META" and accessor is None:
                continue
            inputpins[pinname] = accessor._checksum

        first_output = downstreams[0].write_accessor.target()
        celltypes = {}
        for pinname, accessor in upstreams.items():
            if pinname == "META" and accessor is None:
                continue
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

class TransformerResultUpdateTask(Task):
    def __init__(self, manager, transformer):
        self.transformer = transformer
        super().__init__(manager)
        self._dependencies.append(transformer)

    async def _run(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        transformer = self.transformer
        if transformer._void:
            print("WARNING: transformer %s is void, shouldn't happen during transformer update" % transformer)
            return
        livegraph = manager.livegraph
        downstreams = livegraph.transformer_to_downstream[transformer]
        checksum = transformer._checksum

        if checksum is None:
            manager.cancel_accessors(downstreams, True)
            return

        accessors_to_cancel = []
        for accessor in downstreams:
            if accessor._void or accessor._checksum is not None:
                accessors_to_cancel.append(accessor)
            else:
                manager.taskmanager.cancel_accessor(accessor)

        manager.cancel_accessors(accessors_to_cancel, False)

        # Chance that the above line cancels our own task
        if self._canceled:
            return

        for accessor in downstreams:
            accessor.build_expression(livegraph, checksum)
            accessor._prelim = transformer.preliminary
            AccessorUpdateTask(manager, accessor).launch()


from .accessor_update import AccessorUpdateTask
from ...status import StatusReasonEnum
from . import is_equal