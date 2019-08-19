import asyncio
from . import Task
from ...build_module import build_module_async
from ...macro_mode import get_macro_mode

class MacroUpdateTask(Task):
    def __init__(self, manager, macro):
        self.macro = macro
        super().__init__(manager)
        self.dependencies.append(macro)

    async def _run(self):
        while get_macro_mode():
            await asyncio.sleep(0)
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
            if accessor._void: #upstream error
                status_reason = StatusReasonEnum.UPSTREAM

        if status_reason is not None:
            if not macro._void:
                print("WARNING: macro %s is not yet void, shouldn't happen during macro update" % macro)
                macro._status_reason = StatusReasonEnum.UPSTREAM
                return
            return

        for pinname, accessor in upstreams.items():
            if accessor._checksum is None: #pending
                macro._void = False
                return
        
        inputpins = {}
        for pinname, accessor in upstreams.items():
            inputpins[pinname] = accessor._checksum
        if is_equal(inputpins, macro._last_inputs):
            if not macro._void:
                return

        macro._last_inputs = inputpins.copy()
        macro._void = False
        macro._status_reason = None
        
        buffer_cache = manager.cachemanager.buffer_cache        

        code = None
        values = {}
        module_workspace = {}        
        for pinname, accessor in upstreams.items():
            expression_checksum = await EvaluateExpressionTask(
                manager,
                accessor.expression
            ).run()
            celltype = accessor.write_accessor.celltype
            subcelltype = accessor.write_accessor.subcelltype
            buffer = await get_buffer_async(expression_checksum, buffer_cache)
            assert buffer is not None
            value = await deserialize(buffer, expression_checksum, celltype, False)
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
from .evaluate_expression import EvaluateExpressionTask
from ...protocol.get_buffer import get_buffer_async
from ...protocol.deserialize import deserialize
from . import is_equal
from ...status import StatusReasonEnum
from ...cache import CacheMissError