from . import Task
from ...build_module import build_module_async

class MacroUpdateTask(Task):
    def __init__(self, manager, macro):
        self.macro = macro
        super().__init__(manager)
        self.dependencies.append(macro)

    async def _run(self):
        macro = self.macro
        from . import SerializeToBufferTask
        manager = self.manager()
        livegraph = manager.livegraph
        taskmanager = manager.taskmanager
        await taskmanager.await_upon_connection_tasks(self.taskid)
        upstreams = livegraph.macro_to_upstream[macro]
        
        for pinname, accessor in upstreams.items():
            if accessor is None: #unconnected
                macro._status_reason = StatusReasonEnum.UNCONNECTED
                return                
        status_reason = None        
        for pinname, accessor in upstreams.items():
            if accessor._void or accessor._checksum is None: #undefined/upstream error
                reason = StatusReasonEnum.UPSTREAM
            else:
                continue
            if status_reason is None or reason < status_reason:                
                status_reason = reason
        macro._status_reason = status_reason

        if status_reason is not None:
            if not macro._void:
                print("WARNING: macro %s is not yet void, shouldn't happen during transformer update" % macro)
                manager.cancel_macro(macro, void=True)
                return
            return

        inputpins = {}
        for pinname, accessor in upstreams.items():
            inputpins[pinname] = accessor._checksum
        if is_equal(inputpins, macro._last_inputs):
            if not macro._void:
                return

        macro._last_inputs = inputpins.copy()
        macro._void = False
        
        buffer_cache = manager.cachemanager.buffer_cache        

        code = None
        values = {}
        module_workspace = {}        
        for pinname, accessor in upstreams.items():
            checksum = inputpins[pinname]
            celltype = accessor.write_accessor.celltype
            subcelltype = accessor.write_accessor.subcelltype
            buffer = await get_buffer_async(checksum, buffer_cache)
            assert buffer is not None
            value = await deserialize(buffer, checksum, celltype, False)
            if value is None:
                raise CacheMissError(pinname, codename)
            if pinname == "code":
                code = value
            elif (celltype, subcelltype) == ("plain", "module"):
                mod = await build_module_async(value)
                module_workspace[pinname] = mod[1]
            else:
                values[pinname] = value

        macro._execute(code, values, module_workspace)

from .accessor_update import AccessorUpdateTask
from ...protocol.get_buffer import get_buffer_async
from ...protocol.deserialize import deserialize
from . import is_equal
from ...status import StatusReasonEnum
from ...cache import CacheMissError