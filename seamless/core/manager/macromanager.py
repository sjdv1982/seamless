import weakref
import asyncio
import time
import logging
import traceback
import pprint

from ..build_module import build_all_modules
from ..macro_mode import get_macro_mode

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

async def _prepare(macro, manager, max_running_tasks):
    if manager is None or manager._destroyed:
        return
    livegraph = manager.livegraph
    taskmanager = manager.taskmanager
    tasks = taskmanager.tasks

    while len(tasks) >= max_running_tasks:
        await asyncio.sleep(0.001)

    if macro._destroyed:
        return

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
            print_debug("ABORT", macro, " <= pinname", pinname)
            manager.cancel_macro(macro, False)
            return

    inputpins = {}
    for pinname, accessor in upstreams.items():
        inputpins[pinname] = accessor._checksum

    cachemanager = manager.cachemanager
    if is_equal(inputpins, macro._last_inputs):
        if not macro._in_elision:
            if cachemanager.macro_exceptions.get(macro) is not None:
                assert macro._gen_context is None
                macro._void = True
            return

    macro._last_inputs = inputpins.copy()

    if elide(macro):
        macro._in_elision = True
        if cachemanager.macro_exceptions.get(macro) is not None:
            assert macro._gen_context is None
            macro._void = True
        return

    macro._in_elision = False

    code = None
    values = {}
    modules_to_build = {}
    for pinname, accessor in sorted(upstreams.items(),key=lambda item: item[0]):
        if accessor._checksum is None: #pending, a legitimate use case, but we can't proceed
            print_debug("ABORT", macro, " <= pinname", pinname)
            manager.cancel_macro(macro, False)
            return
        if accessor.expression.hash_pattern is not None:
            raise NotImplementedError
        expression_checksum = await EvaluateExpressionTask(
            manager,
            accessor.expression
        ).run()
        celltype = accessor.write_accessor.celltype
        subcelltype = accessor.write_accessor.subcelltype
        buffer = await cachemanager.fingertip(expression_checksum)
        assert buffer is not None
        value = await deserialize(buffer, expression_checksum, celltype, True)
        if value is None:
            raise CacheMissError(pinname)
        pinname2 = pinname
        pin = macro._pins[pinname]
        if pin.as_ is not None:
            pinname2 = pin.as_

        if pinname == "code":
            code = value
        elif (celltype, subcelltype) == ("plain", "module"):
            modules_to_build[pinname2] = value
        else:
            values[pinname2] = value

    module_workspace = {}
    
    root = macro._root()
    compilers = getattr(root,"_compilers", default_compilers)
    languages = getattr(root,"_languages", default_languages)
    build_all_modules(
        modules_to_build, module_workspace,
        compilers=compilers,
        languages=languages,
        module_debug_mounts=None
    )
    return code, values, module_workspace


class MacroManager:
    MAX_RUNNING_TASKS = 50
    WAIT_FOR_SIBLING = 3  # how many seconds to wait for a sibling macro that has a higher path priority
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.macros = set()
        self.macros_prepared = {}
        self.preparing_tasks = {}
        self._destroyed = False
        self.runner = asyncio.ensure_future(self.run())
        self._consider_update = (None, None)

    @property
    def queued(self):
        return len(self.macros_prepared) or len(self.preparing_tasks)

    async def _prepare_macro(self, macro):
        try:
            while 1:
                try:
                    pos = list(self.preparing_tasks.keys()).index(macro)
                except ValueError:
                    return
                if len(self.macros_prepared) + pos <= 10:
                    break
                await asyncio.sleep(0.01)
            result = await _prepare(macro, self.manager(), self.MAX_RUNNING_TASKS)
            if result is not None:
                self.macros_prepared[macro] = result
        except Exception:
            traceback.print_exc()
        finally:
            self.preparing_tasks.pop(macro, None)

    def _update_next_macro(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        if len(manager.taskmanager.tasks) + len(manager.taskmanager.upon_connection_tasks) > self.MAX_RUNNING_TASKS:
            return
        if not self.macros_prepared:
            return
        def build_macrokeys(macros, parent_macro=0):
            macrokeys00 = [
                ((macro._get_macro() if parent_macro == 0 else parent_macro),
                macro.path, macro) for macro in macros
            ]
            macrokeys0 = [((m[0].path if m[0] is not None else ()), m[0], m[1], m[2]) for m in macrokeys00]
            macrokeys = [(-len(m[0]), m[0], -len(m[2]), m[2], m[1], m[3]) for m in macrokeys0]
            return macrokeys
        macrokeys = sorted(build_macrokeys(self.macros_prepared))
        macrokey = macrokeys[0]
        _, _, _, _, parent_macro, macro = macrokey
        proceed = False
        sibling_macros = [m for m in self.macros \
            if m is macro or \
            (m._gen_context is None and not m._void and m._get_macro() is parent_macro)]
        if len(sibling_macros) == 1:
            proceed = True
        else:
            sibling_macrokeys = build_macrokeys(sibling_macros, parent_macro=parent_macro)
            #pprint.pprint(sibling_macrokeys)
            if sorted(sibling_macrokeys)[0] == macrokey:
                proceed = True
            elif self.WAIT_FOR_SIBLING == 0:
                proceed = True
            elif self._consider_update[0] is macro:
                if time.time() - self._consider_update[1] > self.WAIT_FOR_SIBLING:
                    proceed = True
        if not proceed:
            if self._consider_update[0] is not macro:
                self._consider_update = (macro, time.time())
            return
        #print("UPDATE MACRO", macro, len(macrokeys))

        code, values, module_workspace = self.macros_prepared.pop(macro)
        if macro._gen_context is not None:
            macro._gen_context.destroy()
            macro._gen_context = None
        macro._execute(code, values, module_workspace)
        #print("/UPDATE MACRO", macro, len(macrokeys))


    def _kludge(self):
        # Temporary band-aid for https://github.com/sjdv1982/seamless/issues/142
        stale = [m for m in self.macros if m.status == "Status: pending"]
        for m in stale:
            self.update_macro(m)

    async def run(self):
        while not self._destroyed:
            try:
                self._update_next_macro()
            except Exception:
                traceback.print_exc()
            await asyncio.sleep(0.001)

    def register_macro(self, macro):
        assert macro not in self.macros
        self.macros.add(macro)

    def update_macro(self, macro):
        assert macro in self.macros
        if macro in self.preparing_tasks:
            return
        self.preparing_tasks[macro] = asyncio.ensure_future(
            self._prepare_macro(macro)
        )

    def cancel_macro(self, macro):
        assert macro in self.macros
        self.macros_prepared.pop(macro, None)
        if macro in self.preparing_tasks:
            t = self.preparing_tasks.pop(macro)
            t.cancel()
    
    def destroy_macro(self, macro):
        self.cancel_macro(macro)
        self.macros.remove(macro)

    def destroy(self):
        self._destroyed = True

from .tasks.accessor_update import AccessorUpdateTask
from .tasks.evaluate_expression import EvaluateExpressionTask
from ..protocol.get_buffer import get_buffer
from ..protocol.deserialize import deserialize
from .tasks import is_equal
from ..status import StatusReasonEnum
from ..cache.elision import elide
from ..cache import CacheMissError
from ...compiler import compilers as default_compilers, languages as default_languages