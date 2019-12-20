from . import Task
import traceback
import copy

def overlap_path(p1, p2):
    if p1[:len(p2)] == p2:
        return True    
    elif p2[:len(p1)] == p1:
        return True
    else:
        return False

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
        #print("RUN", sc._auth_value, "/RUN")
        for out_path in sc.outchannels:
            """
            # Done before...
            for mod_path in modified_paths:
                if overlap_path(out_path, mod_path):
                    manager.cancel_cell_path(sc._data, out_path, False)
                    break
            """
            curr_prelim = False
            for in_path in sc.inchannels:
                if overlap_path(in_path, out_path):
                    curr_prelim = sc.inchannels[in_path]._prelim
                    break
            prelim[out_path] = curr_prelim
        value, checksum = None, None
        ok = True
        if len(sc.inchannels):
            paths = sorted(list(sc.inchannels))            
            if paths == [()] and not sc.hash_pattern:
                checksum = sc.inchannels[()]._checksum
                assert checksum is None or isinstance(checksum, bytes), checksum
            else:
                if not sc.no_auth:                    
                    value = copy.deepcopy(sc._auth_value)
                    if value is None:
                        if sc.auth._checksum is not None:
                            checksum = sc.auth._checksum
                            value = copy.deepcopy(sc.auth.data)
                            sc._auth_value = value
                    else:
                        auth_buf = await SerializeToBufferTask(
                            manager, value, "mixed", use_cache=False # the value object changes all the time...
                        ).run()
                        auth_checksum = await CalculateChecksumTask(manager, auth_buf).run()                        
                        auth_checksum = auth_checksum.hex()
                        sc.auth._set_checksum(auth_checksum, from_structured_cell=True)                        
                        if not len(paths):
                            checksum = auth_checksum
                if value is None:
                    if isinstance(paths[0], int):
                        value = []
                    else:
                        value = {}
                for path in paths:                    
                    subchecksum = sc.inchannels[path]._checksum
                    if subchecksum is not None:
                        try:
                            buffer = await GetBufferTask(manager, subchecksum).run()
                            subvalue = await DeserializeBufferTask(
                                manager, buffer, subchecksum, "mixed", False
                            ).run()
                            await set_subpath(value, sc.hash_pattern, path, subvalue)
                            """
                            # Do we need this? 
                            # It messes up "value is None" checks in subsequent joins,
                            #  preventing the reading from value from .auth when it should
                            if not sc.no_auth:
                                for mod_path in modified_paths:
                                    if overlap_path(path, mod_path): 
                                        if len(path) and sc._auth_value is None:  # duck tape...
                                            if isinstance(path[0], int):
                                                sc._auth_value = []
                                            else:
                                                sc._auth_value = {}
                                        await set_subpath(sc._auth_value, sc.hash_pattern, path, None)        
                                        break                            
                            """
                        except Exception:
                            sc._exception = traceback.format_exc(limit=0)   
                            ok = False
                            break         
                    else:
                        ###await set_subpath(value, sc.hash_pattern, path, None)
                        ok = False
        else:            
            value = copy.deepcopy(sc._auth_value)
            if value is None:
                if sc.auth._checksum is not None:
                    checksum = sc.auth._checksum                     
                    value = copy.deepcopy(sc.auth.data)
                    sc._auth_value = value
        if not ok:
            value = None
            checksum = None

        if checksum is None and value is not None:
            try:
                buf = await SerializeToBufferTask(
                    manager, value, "mixed", use_cache=False # the value object changes all the time...
                ).run()
                checksum = await CalculateChecksumTask(manager, buf).run()
            except Exception:
                sc._exception = traceback.format_exc(limit=0)   
                ok = False         
        if checksum is not None:
            if isinstance(checksum, bytes):
                checksum = checksum.hex()        
            if not len(sc.inchannels):            
                sc.auth._set_checksum(checksum, from_structured_cell=True)
            if sc.buffer is not sc.auth:            
                sc.buffer._set_checksum(checksum, from_structured_cell=True)
            if sc.schema is not None and value is None:
                cs = bytes.fromhex(checksum)
                buf = await GetBufferTask(manager, cs).run()
                value = await DeserializeBufferTask(manager, buf, cs, "mixed", copy=False).run()
        
        if ok and value is not None and sc.schema is not None:
            schema = sc.get_schema()
            if schema is not None:
                if sc.hash_pattern is None:
                    value2 = copy.deepcopy(value)
                else:
                    mode, value2 = await get_subpath(value, sc.hash_pattern, ())
                    assert mode == "value"
                s = Silk(data=value2, schema=schema)            
                try:
                    s.validate()
                    sc._exception = None
                except ValidationError:
                    sc._exception = traceback.format_exc(limit=0)
                    ok = False
                    sc._data._set_checksum(None, from_structured_cell=True)                    
                    for out_path in sc.outchannels:
                        manager.cancel_cell_path(sc._data, out_path, True)
        if ok:
            if checksum is not None and sc._data is not sc.buffer:
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
                expression_to_checksum = manager.cachemanager.expression_to_checksum
                for out_path in sc.outchannels:                    
                    if sc._new_connections:
                        changed = True
                    else:
                        changed = False
                        for mod_path in modified_paths:
                            if overlap_path(out_path, mod_path): 
                                changed = True
                                break
                    changed = True ### duck tape...           
                    if changed:
                        for accessor in downstreams[out_path]:
                            changed2 = accessor.build_expression(livegraph, cs)
                            if prelim[out_path] != accessor._prelim:
                                accessor._prelim = prelim[out_path]
                                changed2 = True
                            if changed2:
                                AccessorUpdateTask(manager, accessor).launch()
                    elif cs is not None: # morph
                        # TODO: for now, will not be triggered
                        for accessor in downstreams[out_path]:                                
                            old_expression = accessor.expression
                            expression_result_checksum = \
                                expression_to_checksum.get(old_expression)
                            if expression_result_checksum is not None:
                                accessor.build_expression(livegraph, cs)
                                new_expression = accessor.expression
                                expression_to_checksum[new_expression] = \
                                    expression_result_checksum
            sc.modified_auth_paths.clear()
            sc.modified_inchannels.clear()
            sc._new_connections = False

from .serialize_buffer import SerializeToBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .get_buffer import GetBufferTask
from .checksum import CalculateChecksumTask
from .accessor_update import AccessorUpdateTask
from ....silk.Silk import Silk, ValidationError
from ...protocol.expression import get_subpath, set_subpath