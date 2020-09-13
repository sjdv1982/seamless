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
            if not isinstance(task, UponConnectionTask):
                if sc not in task.dependencies:
                    continue
                if task.taskid >= self.taskid or task.future is None:
                    continue
            tasks.append(task)
        if len(tasks):
            await taskmanager.await_tasks(tasks, shield=True)
            await self.await_sc_tasks()


    async def _run(self):
        from ...status import StatusReasonEnum
        manager = self.manager()
        sc = self.structured_cell
        await self.await_sc_tasks()
        task_canceled = False
        if sc._data is not sc.auth and sc._data._checksum is not None:
            print("{} should have been canceled!".format(sc), file=sys.stderr)
            return

        locknr = await acquire_evaluation_lock(self)
        if sc._data._void:
            print("{} should not be void!".format(sc), file=sys.stderr)
            return
            #import traceback
            #traceback.print_stack()
        if sc._equilibrated:
            print("{} should not be marked as equilibrated!".format(sc), file=sys.stderr)
            return
            #import traceback
            #traceback.print_stack()

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
                            value = copy.deepcopy(sc._auth_value)
                            if value is None or sc._auth_temp_checksum is not None:
                                if sc.auth._checksum is not None or sc._auth_temp_checksum is not None:
                                    ### value = copy.deepcopy(sc.auth.data)  # Not necessarily up to date (?)
                                    auth_checksum = sc.auth._checksum
                                    if sc._auth_temp_checksum is not None:
                                        auth_checksum = sc._auth_temp_checksum
                                    buffer = await GetBufferTask(manager, auth_checksum).run()
                                    if buffer is None:
                                        raise CacheMissError(auth_checksum.hex())
                                    value = await DeserializeBufferTask(
                                        manager, buffer, auth_checksum, "mixed", True
                                    ).run()
                                    sc._auth_value = copy.deepcopy(value)
                                    sc._auth_temp_checksum = None
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
                        for path in paths:
                            subchecksum = sc.inchannels[path]._checksum
                            if subchecksum is not None:
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
                if value is None or sc._auth_temp_checksum is not None:
                    if sc.auth._checksum is not None or sc._auth_temp_checksum is not None:
                        checksum = sc.auth._checksum
                        if sc._auth_temp_checksum is not None:
                            checksum = sc._auth_temp_checksum
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
                            sc._auth_temp_checksum = None
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
                except CacheMissError:
                    sc._exception = traceback.format_exc(limit=0)
                    ok = False
                except Exception:
                    sc._exception = traceback.format_exc()
                    ok = False
            if ok:
                assert checksum is not None
                if isinstance(checksum, bytes):
                    checksum = checksum.hex()
                if not len(sc.inchannels):
                    sc.auth._set_checksum(checksum, from_structured_cell=True)
                if sc.buffer is not sc.auth:
                    #if checksum is not None and (str(sc).find("inp.b") > -1 or str(sc).find("inp.a") > -1):
                    #    print("STRUC SET CELL CHECKSUM", sc, checksum[:10], "TASK:", self.taskid)
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

            modified = sc._modified or sc._modified_schema
            self.ok = ok
            if ok:
                cancel_paths = []
                if checksum is not None and sc._data is not sc.auth:
                    sc._data._set_checksum(checksum, from_structured_cell=True)

                if len(sc.outchannels):
                    livegraph = manager.livegraph
                    cachemanager = manager.cachemanager
                    downstreams = livegraph.paths_to_downstream[sc._data]
                    cs = bytes.fromhex(checksum) if checksum is not None else None
                    expression_to_result_checksum = cachemanager.expression_to_result_checksum
                    #print("SC VALUE", self, sc, value)
                    for out_path in sc.outchannels:
                        if cs is None:
                            cancel_paths.append(out_path)
                        else:
                            for accessor in downstreams[out_path]:
                                changed = False
                                if modified:
                                    changed = True

                                if accessor.expression is None:
                                    changed = True

                                #print("!SC VALUE", out_path, accessor._checksum, modified, accessor.expression is None, changed)
                                if changed:
                                    accessor.build_expression(livegraph, cs)
                                    accessor._soften = True
                                    accessor._prelim = prelim[out_path]
                                    AccessorUpdateTask(manager, accessor).launch()
                                else:
                                    old_expression = accessor.expression
                                    expression_result_checksum = expression_to_result_checksum.get(old_expression)
                                    accessor.build_expression(livegraph, cs)
                                    new_expression = accessor.expression
                                    if expression_result_checksum != cs:
                                        cachemanager.incref_checksum(
                                            expression_result_checksum,
                                            new_expression,
                                            False,
                                            True
                                        )
                                    accessor._prelim = prelim[out_path]

                    #print("/SC VALUE", sc, value)

                sc._exception = None
                # Do this even if cancel_paths is empty.
                # If there are no more pending inchannels, the cancel system
                #  will now unsoften any outchannel accessors that resolve to None, causing them to be void
                manager.cancel_scell(sc, self, cancel_paths)
                sc._modified = False
                sc._modified_schema = False
            else:
                if not task_canceled:
                    # The cancel system may now decide to put the scell into void state
                    #  depending if there are pending inchannels or not
                    manager.cancel_scell(sc, self)
            #print("/JOIN", sc, ok, value, self)
        finally:
            release_evaluation_lock(locknr)

from .serialize_buffer import SerializeToBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .get_buffer import GetBufferTask
from .checksum import CalculateChecksumTask
from .accessor_update import AccessorUpdateTask
from .upon_connection import UponConnectionTask
from ...cache import CacheMissError
from ...cache.buffer_cache import buffer_cache
from ....silk.Silk import Silk, ValidationError
from ...protocol.expression import get_subpath, set_subpath, set_subpath_checksum, access_hash_pattern
from . import acquire_evaluation_lock, release_evaluation_lock