from . import Task
import sys
import traceback
import copy
import asyncio
from asyncio import CancelledError

from ...utils import overlap_path

class StructuredCellTask(Task):
    def __init__(self, manager, structured_cell):
        super().__init__(manager)
        self.structured_cell = structured_cell
        self._dependencies.append(structured_cell)

    async def await_sc_tasks(self, auth, _iter=0):
        sc = self.structured_cell
        manager = self.manager()
        taskmanager = manager.taskmanager
        tasks = []
        for task in taskmanager.tasks:
            if task is self:
                continue
            if not isinstance(task, UponConnectionTask):
                if sc not in task.dependencies:
                    continue
                if auth:
                    if not isinstance(task, StructuredCellAuthTask):
                        continue
                    if task.taskid >= self.taskid or task.future is None:
                        continue
                else:
                    if not isinstance(task, StructuredCellAuthTask):
                        if task.taskid >= self.taskid or task.future is None:
                            continue
            if task.future is not None and task.future.done():
                continue
            tasks.append(task)
        if len(tasks):
            if _iter == 10:
                raise Exception(tasks[:10], self) # could not wait for tasks
            futures0 = [task.future for future in tasks]
            futures = [future for future in futures0 if future is not None]
            if not len(futures):
                await asyncio.sleep(0.05)
            else:
                await asyncio.wait(futures, timeout=0.2)  # sometimes, this goes wrong, which is why the timeout is needed
            await self.await_sc_tasks(auth, _iter=_iter+1)


class StructuredCellAuthTask(StructuredCellTask):
    async def _run(self):
        manager = self.manager()
        sc = self.structured_cell
        await self.await_sc_tasks(auth=True)

        value = sc._auth_value

        locknr = await acquire_evaluation_lock(self)
        try:
            if value is None:
                sc._auth_invalid = True
                auth_checksum = None
            else:
                auth_buf = await SerializeToBufferTask(
                    manager, value, "mixed",
                    use_cache=False  # the auth_value object can be modified by Silk at any time
                ).run()
                auth_checksum = await CalculateChecksumTask(manager, auth_buf).run()
                buffer_cache.cache_buffer(auth_checksum, auth_buf)
                auth_checksum = auth_checksum.hex()
            sc.auth._set_checksum(auth_checksum, from_structured_cell=True)
        except CancelledError as exc:
            if self._canceled:
                raise exc from None
            sc._exception = traceback.format_exc(limit=0)
            sc._auth_invalid = True
        except CacheMissError:  # should not happen: we keep refs-to-auth!
            sc._exception = traceback.format_exc(limit=0)
            sc._auth_invalid = True
        except Exception:
            sc._exception = traceback.format_exc()
            sc._auth_invalid = True
        else:
            sc._auth_value = None
            if auth_checksum is not None:
                sc._auth_invalid = False
        finally:
            release_evaluation_lock(locknr)
            if not self._canceled:
                taskmanager = manager.taskmanager
                ok = (not sc._auth_invalid)
                def func():
                    sc._auth_joining = False
                    manager.structured_cell_trigger(sc, void=(not ok))
                taskmanager.add_synctask(
                    func , (), {}, False
                )


class StructuredCellJoinTask(StructuredCellTask):

    async def _run(self):
        from ...status import StatusReasonEnum
        manager = self.manager()
        sc = self.structured_cell
        await self.await_sc_tasks(auth=False)
        task_canceled = False

        if sc._data is not sc.auth and sc._data._checksum is not None:
            print("{} should have been canceled!".format(sc), file=sys.stderr)

        if sc._data._void:
            print("{} should not be void!".format(sc), file=sys.stderr)
            return


        if sc._mode != SCModeEnum.FORCE_JOINING:
            for inchannel in sc.inchannels.values():
                if inchannel._checksum is None and not inchannel._void:
                    # Refuse to join while pending.
                    return

        locknr = await acquire_evaluation_lock(self)
        #print("JOIN", sc)

        try:
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
            has_auth = False
            has_inchannel = False
            if len(sc.inchannels):
                paths = sorted(list(sc.inchannels))
                if paths == [()] and not sc.hash_pattern:
                    checksum = sc.inchannels[()]._checksum
                    assert checksum is None or isinstance(checksum, bytes), checksum
                    if checksum is None:
                        ok = False
                else:
                    try:
                        if not sc.no_auth:
                            auth_checksum = sc.auth._checksum
                            if sc._auth_invalid:
                                ok = False
                            else:
                                if auth_checksum is not None:
                                    buffer = await GetBufferTask(manager, auth_checksum).run()
                                    if buffer is None:
                                        raise CacheMissError(auth_checksum.hex())
                                    value = await DeserializeBufferTask(
                                        manager, buffer, auth_checksum, "mixed", copy=True
                                    ).run()
                                    if value is not None:
                                        has_auth = True
                                checksum = None  # needs to be re-computed after updating with inchannels
                    except CacheMissError: # shouldn't happen; we keep refs-to-auth!
                        sc._exception = traceback.format_exc(limit=0)
                        ok = False
                    except (TypeError, ValueError, KeyError):
                        sc._exception = traceback.format_exc(limit=0)
                        ok = False
                    except CancelledError as exc:
                        if self._canceled:
                            raise exc from None
                        else:
                            sc._exception = traceback.format_exc()
                            ok = False
                    except Exception as exc:
                        sc._exception = traceback.format_exc()
                        ok = False
                    if ok:
                        if value is None:
                            if isinstance(paths[0], int):
                                value = []
                            elif isinstance(paths[0], (list, tuple)) and len(paths[0]) and isinstance(paths[0][0], int):
                                value = []
                            else:
                                if sc.hash_pattern is not None:
                                    if isinstance(sc.hash_pattern, dict):
                                        for k in sc.hash_pattern:
                                            if k.startswith("!"):
                                                value = []
                                                break
                                if value is None:
                                    value = {}
                        assert value is not None
                        for path in paths:
                            subchecksum = sc.inchannels[path]._checksum
                            if subchecksum is not None:
                                has_inchannel = True
                                try:
                                    # - no need to buffer-cache, since the inchannel holds a ref
                                    # - the subchecksum has already the correct hash pattern (accessors make sure of this)

                                    sub_buffer = None
                                    if sc.hash_pattern is None or access_hash_pattern(sc.hash_pattern, path) != "#":
                                        sub_buffer = await GetBufferTask(manager, subchecksum).run()
                                    await set_subpath_checksum(value, sc.hash_pattern, path, subchecksum, sub_buffer)
                                except CancelledError as exc:
                                    if self._canceled:
                                        raise exc from None
                                    ok = False
                                    task_canceled = True
                                    break
                                except CacheMissError:
                                    sc._exception = traceback.format_exc(limit=0)
                                    sc._data._status_reason = StatusReasonEnum.INVALID
                                    ok = False
                                    break
                                except (TypeError, ValueError, KeyError):
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
                checksum = sc.auth._checksum
                if checksum is not None:
                    try:
                        buffer = await GetBufferTask(manager, checksum).run()
                    except CacheMissError: # should not happen: we keep refs-to-auth!
                        sc._exception = traceback.format_exc(limit=0)
                        ok = False
                    else:
                        value = await DeserializeBufferTask(
                            manager, buffer, checksum, "mixed", copy=True
                        ).run()
                        if value is not None:
                            has_auth = True
                else:
                    ok = False
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
                    assert checksum is not None
                    buffer_cache.cache_buffer(checksum, buf)
                except CancelledError as exc:
                    if self._canceled:
                        raise exc from None
                    ok = False
                    task_canceled = True
                except CacheMissError:  # shouldn't happen; checksum is fresh
                    sc._exception = traceback.format_exc(limit=0)
                    ok = False
                except Exception:
                    sc._exception = traceback.format_exc()
                    ok = False
            if ok:
                assert checksum is not None
                if isinstance(checksum, bytes):
                    checksum = checksum.hex()
                if sc.buffer is not sc.auth:
                    #if checksum is not None and (str(sc).find("inp.b") > -1 or str(sc).find("inp.a") > -1):
                    #    print("STRUC SET CELL CHECKSUM", sc, checksum[:10], "TASK:", self.taskid)
                    sc.buffer._set_checksum(checksum, from_structured_cell=True)
                if schema is not None and value is None:
                    cs = bytes.fromhex(checksum)
                    try:
                        buf = await GetBufferTask(manager, cs).run()
                    except CacheMissError:  # shouldn't happen; checksum is fresh
                        sc._exception = traceback.format_exc(limit=0)
                        ok = False
                    else:
                        value = await DeserializeBufferTask(manager, buf, cs, "mixed", copy=False).run()

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

            if sc._mode != SCModeEnum.FORCE_JOINING:
                for inchannel in sc.inchannels.values():
                    if inchannel._checksum is None and not inchannel._void:
                        # We have become pending. Return
                        if not sc._auth_invalid:
                            sc._exception = None
                        return

            if ok:
                if len(sc.outchannels):
                    livegraph = manager.livegraph
                    cachemanager = manager.cachemanager
                    downstreams = livegraph.paths_to_downstream[sc._data]
                    cs = bytes.fromhex(checksum)
                    expression_to_result_checksum = cachemanager.expression_to_result_checksum
                    taskmanager = manager.taskmanager

                    accessors_to_cancel = []
                    for out_path in sc.outchannels:
                        for accessor in downstreams[out_path]:
                            if accessor._void or accessor._checksum is not None:
                                accessors_to_cancel.append(accessor)
                            else:
                                taskmanager.cancel_accessor(accessor)

                    if len(accessors_to_cancel):
                        manager.cancel_accessors(accessors_to_cancel, False)

                    # Chance that the above line cancels our own task
                    if self._canceled:
                        return

                    for out_path in sc.outchannels:
                        for accessor in downstreams[out_path]:
                            #print("!SC VALUE", sc, out_path, accessor._void)
                            #  manager.cancel_accessor(accessor)  # already done above
                            accessor.build_expression(livegraph, cs)
                            accessor._prelim = prelim[out_path]
                            AccessorUpdateTask(manager, accessor).launch()

            if ok:
                if has_auth or has_inchannel:
                    assert checksum is not None
                if sc._data is not sc.auth:
                    sc._data._set_checksum(checksum, from_structured_cell=True)
                sc._exception = None

            for inchannel in sc.inchannels.values():
                inchannel._save_state()
        finally:
            release_evaluation_lock(locknr)
            if not self._canceled:
                taskmanager = manager.taskmanager
                def func():
                    sc._joining = False
                    manager.structured_cell_trigger(sc, void=(not ok))
                taskmanager.add_synctask(
                    func , (), {}, False
                )

from .serialize_buffer import SerializeToBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .get_buffer import GetBufferTask
from .checksum import CalculateChecksumTask
from .accessor_update import AccessorUpdateTask
from .upon_connection import UponConnectionTask
from ...cache import CacheMissError
from ...cache.buffer_cache import buffer_cache
from ....silk.Silk import Silk, ValidationError
from ..cancel import get_scell_state, SCModeEnum
from ...protocol.expression import get_subpath, set_subpath, set_subpath_checksum, access_hash_pattern
from . import acquire_evaluation_lock, release_evaluation_lock