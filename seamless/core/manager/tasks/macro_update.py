import asyncio
from . import Task
from ...build_module import build_module_async
from ...macro_mode import get_macro_mode

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

class MacroUpdateTask(Task):
    def __init__(self, manager, macro):
        self.macro = macro
        super().__init__(manager)
        self._dependencies.append(macro)

    async def _run(self):
        while get_macro_mode():
            await asyncio.sleep(0.01)
        macro = self.macro
        manager = self.manager()
        livegraph = manager.livegraph
        taskmanager = manager.taskmanager
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())

        if macro._void:
            print("WARNING: macro %s is void, shouldn't happen during macro update" % macro)
            manager.cancel_macro(macro, True, StatusReasonEnum.ERROR)
            return

        upstreams = livegraph.macro_to_upstream[macro]

        status_reason = None
        for pinname, accessor in upstreams.items():
            if accessor is None: #unconnected
                status_reason = StatusReasonEnum.UNCONNECTED
                break
        else:
            for pinname, accessor in upstreams.items():
                if accessor._void: #upstream error
                    status_reason = StatusReasonEnum.UPSTREAM

        if status_reason is not None:
            print("WARNING: macro %s is void, shouldn't happen during macro update" % macro)
            manager.cancel_macro(macro, True, status_reason)
            return

        for pinname, accessor in upstreams.items():
            if accessor._checksum is None: #pending, a legitimate use case, but we can't proceed
                print_debug("ABORT", self.__class__.__name__, hex(id(self)), self.dependencies)
                manager.cancel_macro(macro, False)
                return

        inputpins = {}
        for pinname, accessor in upstreams.items():
            inputpins[pinname] = accessor._checksum
        if is_equal(inputpins, macro._last_inputs):
            return

        macro._last_inputs = inputpins.copy()
        cachemanager = manager.cachemanager

        code = None
        values = {}
        module_workspace = {}
        for pinname, accessor in upstreams.items():
            expression_checksum = await EvaluateExpressionTask(
                manager,
                accessor.expression
            ).run()
            if accessor.expression.hash_pattern is not None:
                raise NotImplementedError
            celltype = accessor.write_accessor.celltype
            subcelltype = accessor.write_accessor.subcelltype
            buffer = await cachemanager.fingertip(expression_checksum)
            assert buffer is not None
            value = await deserialize(buffer, expression_checksum, celltype, True)
            if value is None:
                raise CacheMissError(pinname, codename)
            if pinname == "code":
                code = value
            elif (celltype, subcelltype) == ("plain", "module"):
                mod = await build_module_async(value)
                module_workspace[pinname] = mod[1]
            else:
                values[pinname] = value

        if macro._gen_context is not None:
            macro._gen_context.destroy()
            macro._gen_context = None
        macro._execute(code, values, module_workspace)

from .accessor_update import AccessorUpdateTask
from .evaluate_expression import EvaluateExpressionTask
from ...protocol.get_buffer import get_buffer
from ...protocol.deserialize import deserialize
from . import is_equal
from ...status import StatusReasonEnum
from ...cache import CacheMissError