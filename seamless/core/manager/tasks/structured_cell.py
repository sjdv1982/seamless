from . import Task
import sys
import traceback
import copy
from asyncio import CancelledError

from ...utils import overlap_path

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
        from ...status import StatusReasonEnum
        manager = self.manager()
        sc = self.structured_cell
        await self.await_sc_tasks()
        canceled = False
        if sc._data is not sc.auth and sc._data._checksum is not None:
            print("{} should have been canceled!".format(sc), file=sys.stderr)
            return
        modified_outchannels = sc.modified.modified_outchannels
        prelim = {}
        for out_path in sc.outchannels:
            curr_prelim = False
            for in_path in sc.inchannels:
                if overlap_path(in_path, out_path):
                    curr_prelim = sc.inchannels[in_path]._prelim
                    break
            prelim[out_path] = curr_prelim
        value, checksum = None, None
        ok = True
        schema = sc.get_schema()
        if len(sc.inchannels):
            paths = sorted(list(sc.inchannels))
            if paths == [()] and not sc.hash_pattern:
                checksum = sc.inchannels[()]._checksum
                assert checksum is None or isinstance(checksum, bytes), checksum
            else:
                try:
                    if not sc.no_auth:
                        value = copy.deepcopy(sc._auth_value)
                        if value is None:
                            if sc.auth._checksum is not None:
                                ### value = copy.deepcopy(sc.auth.data)  # Not necessarily up to date (?)
                                auth_checksum = sc.auth._checksum
                                buffer = await GetBufferTask(manager, auth_checksum).run()
                                if buffer is None:
                                    raise CacheMissError(auth_checksum.hex())
                                value = await DeserializeBufferTask(
                                    manager, buffer, auth_checksum, "mixed", True
                                ).run()
                                sc._auth_value = value
                        else:
                            auth_buf = await SerializeToBufferTask(
                                manager, value, "mixed",
                                use_cache=False  # the value object changes all the time...
                            ).run()
                            auth_checksum = await CalculateChecksumTask(manager, auth_buf).run()
                            buffer_cache.cache_buffer(auth_checksum, auth_buf)
                            auth_checksum = auth_checksum.hex()
                            sc.auth._set_checksum(auth_checksum, from_structured_cell=True)
                        if not len(paths):
                            checksum = auth_checksum
                        else:
                            checksum = None  # needs to be re-computed after updating with inchannels
                except (CacheMissError, TypeError, ValueError, KeyError):
                    sc._exception = traceback.format_exc(limit=0)
                    ok = False
                except Exception:
                    sc._exception = traceback.format_exc()
                    ok = False
                if ok:
                    if value is None:
                        if isinstance(paths[0], int):
                            value = []
                        elif isinstance(paths[0], (list, tuple)) and len(paths[0]) and isinstance(paths[0][0], int):
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
                                # no need to buffer-cache, since the upstream inchannel accessors hold a ref
                                await set_subpath(value, sc.hash_pattern, path, subvalue)
                            except CancelledError:
                                ok = False
                                canceled = True
                                break
                            except (CacheMissError, TypeError, ValueError, KeyError):
                                sc._exception = traceback.format_exc(limit=0)
                                ok = False
                                break
                            except Exception:
                                sc._exception = traceback.format_exc()
                                ok = False
                                break
                        else:
                            pass  # It is OK to have inchannels at None (undefined)
                                # Else, use required properties in the schema
        else:
            value = copy.deepcopy(sc._auth_value)
            if value is None:
                if sc.auth._checksum is not None:
                    checksum = sc.auth._checksum
                    ### value = copy.deepcopy(sc.auth.data) # Not necessarily up to date (?)
                    try:
                        buffer = await GetBufferTask(manager, checksum).run()
                    except CacheMissError:
                        sc._exception = traceback.format_exc(limit=0)
                        ok = False
                    else:
                        value = await DeserializeBufferTask(
                            manager, buffer, checksum, "mixed", True
                        ).run()
                        sc._auth_value = value
        if not ok:
            value = None
            checksum = None

        if checksum is None and value is not None:
            try:
                buf = await SerializeToBufferTask(
                    manager, value, "mixed",
                    use_cache=False  # the value object changes all the time...
                ).run()
                checksum = await CalculateChecksumTask(manager, buf).run()
                buffer_cache.cache_buffer(checksum, buf)
            except CancelledError:
                ok = False
                canceled = True
            except CacheMissError:
                sc._exception = traceback.format_exc(limit=0)
                ok = False
            except Exception:
                sc._exception = traceback.format_exc()
                ok = False
        if checksum is not None:
            if isinstance(checksum, bytes):
                checksum = checksum.hex()
            if not len(sc.inchannels):
                sc.auth._set_checksum(checksum, from_structured_cell=True)
            if sc.buffer is not sc.auth:
                sc.buffer._set_checksum(checksum, from_structured_cell=True)
            if schema is not None and value is None:
                cs = bytes.fromhex(checksum)
                try:
                    buf = await GetBufferTask(manager, cs).run()
                except CacheMissError:
                    sc._exception = traceback.format_exc(limit=0)
                    ok = False
                else:
                    value = await DeserializeBufferTask(manager, buf, cs, "mixed", copy=False).run()

        if not ok and sc.buffer is not sc.auth:
            manager._set_cell_checksum(sc.buffer, None, void=True, status_reason=StatusReasonEnum.UPSTREAM)

        if ok and value is not None and schema is not None:
            if schema is not None:
                if sc.hash_pattern is None:
                    value2 = copy.deepcopy(value)
                else:
                    mode, value2 = await get_subpath(value, sc.hash_pattern, ())
                    assert mode == "value"
                s = Silk(data=value2, schema=schema)
                try:
                    s.validate()
                except ValidationError:
                    sc._exception = traceback.format_exc(limit=0)
                    ok = False
                    manager._set_cell_checksum(sc._data, None, void=True, status_reason=StatusReasonEnum.UPSTREAM)
        if ok:
            hard_cancel_paths = []
            if checksum is not None and sc._data is not sc.auth:
                sc._data._set_checksum(checksum, from_structured_cell=True)

            if len(sc.outchannels):
                livegraph = manager.livegraph
                cachemanager = manager.cachemanager
                downstreams = livegraph.paths_to_downstream[sc._data]
                cs = bytes.fromhex(checksum) if checksum is not None else None
                expression_to_result_checksum = cachemanager.expression_to_result_checksum
                for out_path in sc.outchannels:
                    changed = False
                    if sc._exception is not None or sc._new_outgoing_connections:
                        changed = True
                    else:
                        for p in modified_outchannels:
                            if overlap_path(p, out_path):
                                changed = True
                                break
                    if changed:
                        if cs is None:
                            hard_cancel_paths.append(out_path)
                        else:
                            for accessor in downstreams[out_path]:
                                changed2 = accessor.build_expression(livegraph, cs)
                                if prelim[out_path] != accessor._prelim:
                                    accessor._prelim = prelim[out_path]
                                    changed2 = True
                                if changed2:
                                    AccessorUpdateTask(manager, accessor).launch()
                    elif cs is not None: # morph
                        try:
                            for accessor in downstreams[out_path]:
                                old_expression = accessor.expression
                                expression_result_checksum = \
                                    expression_to_result_checksum.get(old_expression)
                                if expression_result_checksum is not None:
                                    accessor.build_expression(livegraph, cs)
                                    new_expression = accessor.expression
                        except CacheMissError:
                            sc._exception = traceback.format_exc(limit=0)
                            manager.cancel_scell_hard(sc, self, hard_cancel_paths)
                            return
                        except Exception:
                            sc._exception = traceback.format_exc()
                            manager.cancel_scell_hard(sc, self, hard_cancel_paths)
                            return


            sc.modified.clear()
            sc._new_connections = False
            sc._exception = None
            if len(hard_cancel_paths):
                manager.cancel_scell_hard(sc, self, hard_cancel_paths)
        else:
            if not canceled:
                manager.cancel_scell_hard(sc, self)


from .serialize_buffer import SerializeToBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .get_buffer import GetBufferTask
from .checksum import CalculateChecksumTask
from .accessor_update import AccessorUpdateTask
from ...cache import CacheMissError
from ...cache.buffer_cache import buffer_cache
from ....silk.Silk import Silk, ValidationError
from ...protocol.expression import get_subpath, set_subpath