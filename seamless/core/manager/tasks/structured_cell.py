from . import Task
import traceback
import copy

print("TODO: tasks/structured_cell.py: task to deserialize editchannel, then structured_cell.set_auth_path")

class StructuredCellJoinTask(Task):    
    def __init__(self, manager, structured_cell):
        super().__init__(manager)
        self.structured_cell = structured_cell
        self.dependencies.append(structured_cell)

    async def await_sc_tasks(self):
        sc = self.structured_cell
        manager = self.manager()
        taskmanager = manager.taskmanager
        tasks = []
        for task in taskmanager.tasks:
            if sc not in task.dependencies:
                continue
            if task.taskid >= self.taskid or task.future is None:
                continue
            tasks.append(task)
        if len(tasks):
            await taskmanager.await_tasks(tasks, shield=True)


    async def _run(self):
        manager = self.manager()
        sc = self.structured_cell
        await self.await_sc_tasks()
        modified_paths = set(sc.modified_auth_paths)
        modified_paths.update(set([ic.subpath for ic in sc.modified_inchannels]))
        for out_path in sc.outchannels:
            for mod_path in modified_paths:
                if out_path[:len(mod_path)] == mod_path:
                    manager.cancel_cell_path(sc._data, out_path, False)
                    break
        value, checksum = None, None
        if len(sc.inchannels):
            paths = sorted(list(sc.inchannels))
            if paths == [()]:
                checksum = sc.inchannels[()]._checksum
                assert checksum is None or isinstance(checksum, bytes), checksum
            else:
                if sc.no_auth:
                    value = sc._auth_value
                elif isinstance(paths[0], int):
                    value = []
                else:
                    value = {}
                raise NotImplementedError # livegraph branch
        else:            
            value = sc._auth_value
        if checksum is None and value is not None:
            buf = await SerializeToBufferTask(
                manager, value, "mixed", use_cache=False # the value object changes all the time...
            ).run()
            checksum = await CalculateChecksumTask(manager, buf).run()
        if checksum is not None:
            checksum = checksum.hex()        
        if not len(sc.inchannels):
            sc.auth._set_checksum(checksum, from_structured_cell=True)
        if sc.buffer is not sc.auth:            
            sc.buffer._set_checksum(checksum, from_structured_cell=True)
        ok = True
        if value is not None and sc.schema is not None:
            if len(sc.inchannels):
                raise NotImplementedError # livegraph branch  # see above
            #schema = sc.schema.value  # incorrect, because potentially out-of-sync...
            schema = sc._schema_value
            if schema is not None:
                s = Silk(data=copy.deepcopy(value), schema=schema)                
                try:
                    s.validate()
                except ValidationError:
                    traceback.print_exc()
                    ok = False
                    for out_path in sc.outchannels:
                        manager.cancel_cell_path(sc._data, out_path, True)
        if ok:
            if sc._data is not sc.buffer:
                sc._data._set_checksum(checksum, from_structured_cell=True)

            if len(sc.outchannels):
                livegraph = manager.livegraph
                downstreams = livegraph.paths_to_downstream[sc._data]
                if checksum is not None and value is None:
                    cs = bytes.fromhex(checksum)
                    buf = await GetBufferTask(manager, cs).run()
                    value = await DeserializeBufferTask(manager, buf, cs, "mixed", copy=False).run()
                for out_path in sc.outchannels:
                    for mod_path in modified_paths:
                        if out_path[:len(mod_path)] == mod_path:
                            print("UPDATE!", out_path)
                            for accessor in downstreams[out_path]:
                                changed = accessor.build_expression(livegraph, cs)
                                print("TODO: prelim propagation from inchannel (prelim=False if from auth)")
                                AccessorUpdateTask(manager, accessor).launch()
            sc.modified_auth_paths.clear()
            sc.modified_inchannels.clear()

from .serialize_buffer import SerializeToBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .get_buffer import GetBufferTask
from .checksum import CalculateChecksumTask
from .accessor_update import AccessorUpdateTask
from ....silk.Silk import Silk, ValidationError
from ...protocol.expression import get_subpath