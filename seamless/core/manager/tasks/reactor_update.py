import asyncio
from . import Task
from ...cached_compile import cached_compile

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

class ReactorUpdateTask(Task):
    def __init__(self, manager, reactor):
        self.reactor = reactor
        super().__init__(manager)
        self._dependencies.append(reactor)

    async def _run(self):
        reactor = self.reactor
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        livegraph = manager.livegraph
        rtreactor = livegraph.rtreactors[reactor]
        taskmanager = manager.taskmanager
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())

        editpins = rtreactor.editpins
        editpin_to_cell = livegraph.editpin_to_cell[reactor]
        upstreams = livegraph.reactor_to_upstream[reactor]
        outputpins = [pinname for pinname in reactor._pins \
            if reactor._pins[pinname].io == "output" ]
        all_downstreams = livegraph.reactor_to_downstream[reactor]

        status_reason = None
        for pinname, accessor in upstreams.items():
            if accessor is None: #unconnected
                status_reason = StatusReasonEnum.UNCONNECTED
                break
        else:
            for pinname, accessor in upstreams.items():
                if accessor._void: #upstream error
                    status_reason = StatusReasonEnum.UPSTREAM
        for pinname in outputpins:
            downstreams = all_downstreams.get(pinname, [])
            if not len(downstreams):
                status_reason = StatusReasonEnum.UNCONNECTED

        for pinname in editpins:
            cell = editpin_to_cell[pinname]
            if cell is None:
                reactor._status_reason = StatusReasonEnum.UNCONNECTED

        for pinname in editpins:
            cell = editpin_to_cell[pinname]
            pin = reactor._pins[pinname]
            if pin.must_be_defined:
                if cell._void:
                    reactor._status_reason = StatusReasonEnum.UPSTREAM
                    return

        if status_reason is not None:
            print("WARNING: reactor %s is void, shouldn't happen during reactor update" % reactor)
            manager.cancel_reactor(reactor, True, status_reason)
            return

        for pinname, accessor in upstreams.items():
            assert not accessor._void, (reactor, pinname)
            if accessor._checksum is None: #pending; a legitimate use case, but we can't proceed
                print_debug("ABORT", self.__class__.__name__, hex(id(self)), self.dependencies, " <= pinname", pinname)
                reactor._pending = True
                return

        editpin_checksums = {}
        for pinname in editpins:
            cell = editpin_to_cell[pinname]
            checksum = cell._checksum
            editpin_checksums[pinname] = checksum

        reactor._pending = False

        updated = set()
        new_inputs = {}
        new_inputs2 = {}
        old_checksums = reactor._last_inputs
        if old_checksums is None:
            old_checksums = {}
        for pinname, accessor in upstreams.items():
            old_checksum = old_checksums.get(pinname)
            new_checksum = accessor._checksum
            if old_checksum != new_checksum:
                updated.add(pinname)
            new_inputs[pinname] = new_checksum
            wa = accessor.write_accessor
            new_inputs2[pinname] = wa.celltype, wa.subcelltype
        for pinname in editpins:
            old_checksum = old_checksums.get(pinname)
            new_checksum = editpin_checksums[pinname]
            if new_checksum is not None:
                if old_checksum != new_checksum:
                    updated.add(pinname)
                new_inputs[pinname] = new_checksum
                cell = editpin_to_cell[pinname]
                new_inputs2[pinname] = cell._celltype, cell._subcelltype

        reactor._last_inputs = new_inputs

        if not len(updated):
            return

        checksums = {}
        values = {}
        modules_to_build = {}
        for pinname, accessor in upstreams.items():
            if pinname not in updated:
                continue
            checksum = new_inputs[pinname]
            checksums[pinname] = checksum

        for pinname in updated:
            checksum = new_inputs[pinname]
            celltype, subcelltype = new_inputs2[pinname]
            if checksum is None:
                values[pinname] = None
                continue

            buffer = await GetBufferTask(manager, checksum).run()
            assert buffer is not None
            value = await DeserializeBufferTask(
                manager, buffer, checksum, celltype, True
            ).run()
            if value is None:
                raise CacheMissError(pinname, reactor)
            if pinname in ("code_start", "code_update", "code_stop"):
                code_obj = cached_compile(value, str(reactor))
                values[pinname] = code_obj
            elif (celltype, subcelltype) == ("plain", "module"):
                modules_to_build[pinname] = value
            else:
                values[pinname] = value

        module_workspace = {}
        root = reactor._root()
        compilers = getattr(root,"_compilers", default_compilers)
        languages = getattr(root,"_languages", default_languages)
        build_all_modules(
            modules_to_build, module_workspace,
            compilers=compilers,
            languages=languages,
            module_debug_mounts=None
        )
        rtreactor.module_workspace.update(module_workspace)
        rtreactor.values.update(values)
        rtreactor.updated = updated
        rtreactor.execute()


class ReactorResultTask(Task):
    def __init__(self,
        manager, reactor,
        pinname, value,
        celltype, subcelltype
    ):
        self.reactor = reactor
        super().__init__(manager)
        self._dependencies.append(reactor)
        self.pinname = pinname
        self.value = value
        self.celltype = celltype
        assert celltype is not None
        self.subcelltype = subcelltype

    async def _run(self):
        reactor = self.reactor
        if reactor._void:
            print("WARNING: reactor %s is void, shouldn't happen during reactor result task" % reactor)
            return
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        livegraph = manager.livegraph
        accessors = livegraph.reactor_to_downstream[reactor][self.pinname]
        celltype, subcelltype = self.celltype, self.subcelltype
        pinname = self.pinname
        checksum = None
        if self.value is not None:
            try:
                buffer = await SerializeToBufferTask(
                    manager, self.value, celltype,
                    use_cache=True
                ).run()
                checksum = await CalculateChecksumTask(manager, buffer).run()
            except asyncio.CancelledError as exc:
                if not self._canceled:
                    manager._set_reactor_exception(reactor, pinname, exc)
                raise exc from None
            except Exception as exc:
                manager._set_reactor_exception(reactor, pinname, exc)
                raise exc from None

        if checksum is not None:
            await validate_subcelltype(
                checksum, celltype, subcelltype,
                str(reactor) + ":" + pinname
            )
        if reactor._last_outputs is None:
            reactor._last_outputs = {}
        reactor._last_outputs[pinname] = checksum
        downstreams = livegraph.reactor_to_downstream[reactor][pinname]

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
            AccessorUpdateTask(manager, accessor).launch()

        return None

from ...status import StatusReasonEnum
from .accessor_update import AccessorUpdateTask
from .deserialize_buffer import DeserializeBufferTask
from .serialize_buffer import SerializeToBufferTask
from .checksum import CalculateChecksumTask
from .get_buffer import GetBufferTask
from ...protocol.validate_subcelltype import validate_subcelltype
from ...build_module import build_all_modules
from ....compiler import compilers as default_compilers, languages as default_languages
