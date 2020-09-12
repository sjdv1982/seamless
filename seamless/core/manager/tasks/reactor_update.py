from . import Task
from ...cached_compile import cached_compile

class ReactorUpdateTask(Task):
    def __init__(self, manager, reactor):
        self.reactor = reactor
        super().__init__(manager)
        self.dependencies.append(reactor)

    async def _run(self):
        reactor = self.reactor
        manager = self.manager()
        livegraph = manager.livegraph
        rtreactor = livegraph.rtreactors[reactor]
        taskmanager = manager.taskmanager
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())
        editpins = rtreactor.editpins
        editpin_to_cell = livegraph.editpin_to_cell[reactor]
        upstreams = livegraph.reactor_to_upstream[reactor]

        for pinname, accessor in upstreams.items():
            assert not accessor._void, (reactor, pinname)
            if accessor._checksum is None:
                reactor._pending = True
                return

        editpin_checksums = {}
        for pinname in editpins:
            cell = editpin_to_cell[pinname]
            assert not cell._void, (reactor, pinname)
            checksum = cell._checksum
            if checksum is None:
                raise Exception # authoritative cell cannot be non-void and no checksum
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
        module_workspace = {}
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
                mod = await build_module_async(value)
                module_workspace[pinname] = mod[1]
            else:
                values[pinname] = value

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
        self.dependencies.append(reactor)
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
            except Exception as exc:
                manager._set_reactor_exception(reactor, pinname, exc)
                raise
        if checksum is not None:
            await validate_subcelltype(
                checksum, celltype, subcelltype,
                str(reactor) + ":" + pinname
            )
        if reactor._last_outputs is None:
            reactor._last_outputs = {}
        reactor._last_outputs[pinname] = checksum
        downstreams = livegraph.reactor_to_downstream[reactor][pinname]
        for accessor in downstreams:
            #- construct (not compute!) their expression using the cell checksum
            #  Constructing a downstream expression increfs the cell checksum
            changed = accessor.build_expression(livegraph, checksum)
            # TODO: prelim? tricky for a reactor...
            #- launch an accessor update task
            if changed:
                AccessorUpdateTask(manager, accessor).launch()

        return None

from ...status import StatusReasonEnum
from .accessor_update import AccessorUpdateTask
from .deserialize_buffer import DeserializeBufferTask
from .serialize_buffer import SerializeToBufferTask
from .checksum import CalculateChecksumTask
from .get_buffer import GetBufferTask
from ...protocol.validate_subcelltype import validate_subcelltype
from ...build_module import build_module_async