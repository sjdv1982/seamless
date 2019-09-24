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
        prelim = {}
        for out_path in sc.outchannels:
            for mod_path in modified_paths:
                if out_path[:len(mod_path)] == mod_path:
                    manager.cancel_cell_path(sc._data, out_path, False)
                    break
            curr_prelim = False
            for in_path in sc.inchannels:
                if out_path[:len(in_path)] == in_path:
                    curr_prelim = sc.inchannels[in_path]._prelim
                    break
            prelim[out_path] = curr_prelim
        value, checksum = None, None
        if len(sc.inchannels):
            paths = sorted(list(sc.inchannels))
            if paths == [()]:
                checksum = sc.inchannels[()]._checksum
                assert checksum is None or isinstance(checksum, bytes), checksum
            else:
                if not sc.no_auth:
                    value = copy.deepcopy(sc._auth_value)
                if value is None:
                    if isinstance(paths[0], int):
                        value = []
                    else:
                        value = {}
                for path in paths:
                    checksum = sc.inchannels[path]._checksum
                    if checksum is not None:
                        buffer = await GetBufferTask(manager, checksum).run()
                        subvalue = await DeserializeBufferTask(
                            manager, buffer, checksum, "mixed", False
                        ).run()
                        await set_subpath(value, sc.hash_pattern, path, subvalue)
                        if not sc.no_auth:
                            for mod_path in modified_paths:
                                if path[:len(mod_path)] == mod_path:                                
                                    await set_subpath(sc._auth_value, sc.hash_pattern, None)        
                                    break                            
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
                if checksum is not None:
                    cs = bytes.fromhex(checksum)
                    """
                    if value is None:
                        buf = await GetBufferTask(manager, cs).run()
                        value = await DeserializeBufferTask(manager, buf, cs, "mixed", copy=False).run()
                    """
                else:
                    cs = None
                for out_path in sc.outchannels:
                    for mod_path in modified_paths:
                        if out_path[:len(mod_path)] == mod_path:                            
                            for accessor in downstreams[out_path]:
                                changed = accessor.build_expression(livegraph, cs)                                
                                if prelim[out_path] != accessor._prelim:
                                    accessor._prelim = prelim[out_path]
                                    changed = True
                                if changed:
                                    AccessorUpdateTask(manager, accessor).launch()
            sc.modified_auth_paths.clear()
            sc.modified_inchannels.clear()

from .serialize_buffer import SerializeToBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .get_buffer import GetBufferTask
from .checksum import CalculateChecksumTask
from .accessor_update import AccessorUpdateTask
from ....silk.Silk import Silk, ValidationError
from ...protocol.expression import get_subpath, set_subpath