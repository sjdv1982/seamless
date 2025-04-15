from seamless import Checksum, Buffer, CacheMissError
from . import Task
import sys
import traceback
import copy
import asyncio
import json
from asyncio import CancelledError

from seamless.checksum import empty_dict_checksum
from seamless.checksum.buffer_remote import write_buffer, remote_has_checksum
from seamless.checksum.expression import access_hash_pattern
from seamless.config import get_assistant
from seamless.assistant_client import run_job

from ...utils import overlap_path


def is_empty(cell):
    if cell is None:
        return True
    checksum = cell._checksum
    checksum = Checksum(checksum)
    if not checksum or checksum == empty_dict_checksum:
        return True
    return False


def _build_join_dict(sc):
    any_prelim = False
    join_dict = {}
    if sc.hash_pattern is not None:
        join_dict["hash_pattern"] = sc.hash_pattern
    if not sc.no_auth:
        cs = Checksum(sc.auth._checksum)
        if cs:
            join_dict["auth"] = cs
    schema = sc.get_schema()
    if schema == {}:
        schema = None
    if schema is not None:
        join_dict["schema"] = sc.schema._checksum.hex()
    if len(sc.inchannels):
        jd_inchannels = {}
        for in_path in sc.inchannels:
            ic = sc.inchannels[in_path]
            if ic._prelim:
                any_prelim = True
            checksum = ic._checksum
            checksum = Checksum(checksum)
            if checksum:
                jd_inchannels[json.dumps(in_path)] = checksum
        join_dict["inchannels"] = jd_inchannels
    return join_dict, schema, any_prelim


def build_join_transformation(structured_cell):
    """Creates a pseudo-transformation dict of the structured cell join
    A pseudo-transformation is a transformation with language "<structured cell join>"
    that in fact performs a structured cell join.
    The main use case is to send data-intensive structured cell joins to remote locations
    where the data is.
    """

    join_dict, _, _ = _build_join_dict(structured_cell)
    assert isinstance(join_dict, dict), join_dict
    transformation_dict = {
        "__language__": "<structured_cell_join>",
        "structured_cell_join": join_dict,
    }
    transformation_dict_buffer = Buffer(transformation_dict, "plain")
    transformation = transformation_dict_buffer.get_checksum()
    buffer_cache.cache_buffer(transformation, transformation_dict_buffer)

    return transformation


def _join_dict_to_checksums(join_dict):
    hash_pattern = join_dict.get("hash_pattern")
    checksums = []
    for k in ("auth", "schema"):
        checksum = Checksum(join_dict.get(k))
        if checksum:
            checksums.append(checksum)
    inchannels = join_dict.get("inchannels", {})
    for path, checksum in inchannels.items():
        checksum = Checksum(checksum)
        if hash_pattern is None or access_hash_pattern(hash_pattern, path) not in (
            "#",
            "##",
        ):
            checksums.append(checksum)
    return checksums


async def evaluate_join_transformation_remote(structured_cell) -> Checksum:

    if not get_assistant():
        return
    jtf_checksum = build_join_transformation(structured_cell)
    jtf_buffer = await buffer_cache.get_buffer_async(jtf_checksum)
    assert jtf_buffer is not None
    write_buffer(jtf_checksum, jtf_buffer)
    join_dict = json.loads(jtf_buffer)["structured_cell_join"]
    join_dict_buf = await Buffer.from_async(join_dict, "plain", use_cache=True)
    join_dict_checksum = await join_dict_buf.get_checksum_async()
    write_buffer(join_dict_checksum, join_dict_buf)
    try:
        result = await run_job(
            jtf_checksum,
            tf_dunder=None,
            scratch=structured_cell._data._scratch,
            fingertip=False,
        )
        result = Checksum(result)
    except (CacheMissError, RuntimeError):
        result = None
    return result


def _consider_local_evaluation(join_dict):
    """Checks if the structured cell join can easily (no fingertipping) be evaluated locally"""
    checksums = _join_dict_to_checksums(join_dict)
    for checksum in checksums:
        if buffer_cache.get_buffer(checksum, remote=False) is None:
            buffer_info = buffer_cache.get_buffer_info(
                Checksum(checksum),
                sync_remote=True,
                buffer_from_remote=False,
                force_length=False,
            )
            length = buffer_info.get("length")
            if length is not None and length <= buffer_cache.SMALL_BUFFER_LIMIT:
                continue
            return False
    return True


def _consider_remote_evaluation(join_dict):
    """Checks if the structured cell join can easily (no fingertipping) be evaluated remotely.
    This assumes that the assistant has access to the exact same buffer read folders/servers
    """

    if not get_assistant():
        return False
    checksums = _join_dict_to_checksums(join_dict)
    for checksum in checksums:
        if not remote_has_checksum(checksum):
            return False
    return True


def _update_structured_cell(
    sc, checksum, manager, *, check_canceled, prelim, from_fallback
):
    fallback = manager.get_fallback(sc._data)
    if len(sc.outchannels):
        livegraph = manager.livegraph
        downstreams = livegraph.paths_to_downstream[sc._data]
        cs = Checksum(checksum)
        if fallback is not None:
            cs = fallback._checksum
        taskmanager = manager.taskmanager

        accessors_to_cancel = []
        for out_path in sc.outchannels:
            for accessor in downstreams[out_path]:
                if accessor._void or Checksum(accessor._checksum):
                    accessors_to_cancel.append(accessor)
                else:
                    taskmanager.cancel_accessor(accessor)

        if len(accessors_to_cancel):
            manager.cancel_accessors(accessors_to_cancel, False)

        # Chance that the above line cancels our own task
        if check_canceled():
            return

        for out_path in sc.outchannels:
            for accessor in downstreams[out_path]:
                # print("!SC VALUE", sc, out_path, accessor._void)
                #  manager.cancel_accessor(accessor)  # already done above
                accessor.build_expression(livegraph, cs)
                if prelim is not None:
                    accessor._prelim = prelim[out_path]
                else:
                    accessor._prelim = False
                AccessorUpdateTask(manager, accessor).launch()

    if not from_fallback:
        cs = Checksum(checksum)
        if sc._data is not sc.auth:
            sc._data._set_checksum(cs, from_structured_cell=True)
        manager.trigger_all_fallbacks(sc._data)
    sc._exception = None


def update_structured_cell(sc, checksum, *, from_fallback):
    manager = sc._get_manager()
    return _update_structured_cell(
        sc,
        checksum,
        manager,
        check_canceled=lambda: False,
        prelim=None,
        from_fallback=from_fallback,
    )


class StructuredCellTask(Task):
    def __init__(self, manager, structured_cell):
        super().__init__(manager)
        self.structured_cell = structured_cell
        self._dependencies.append(structured_cell)

    async def await_sc_tasks(self, auth, _iter=0):
        sc = self.structured_cell
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
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
                raise Exception(tasks[:10], self)  # could not wait for tasks
            futures0 = [task.future for task in tasks]
            futures = [future for future in futures0 if future is not None]
            if not len(futures):
                await asyncio.sleep(0.05)
            else:
                await asyncio.wait(
                    futures, timeout=0.2
                )  # sometimes, this goes wrong, which is why the timeout is needed
            await self.await_sc_tasks(auth, _iter=_iter + 1)


class StructuredCellAuthTask(StructuredCellTask):
    async def _run(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        sc = self.structured_cell
        await self.await_sc_tasks(auth=True)

        data_value = (
            sc._auth_value
        )  # obeys hash pattern (if there is one), i.e. is a deep structure not a raw value
        locknr = await acquire_evaluation_lock(self)
        try:
            if data_value is None:
                auth_ch = sc._auth_checksum
                if auth_ch is not None:
                    buffer = await GetBufferTask(manager, auth_ch).run()
                    if buffer is None:
                        raise CacheMissError(auth_ch.hex())
                    data_value = await DeserializeBufferTask(
                        manager, buffer, auth_ch, "mixed", copy=True
                    ).run()
            if data_value is None:
                sc._auth_invalid = True
                auth_checksum = None
            else:
                auth_buf = await SerializeToBufferTask(
                    manager,
                    data_value,
                    "mixed",
                    use_cache=False,  # the auth_value object can be modified by Silk at any time
                ).run()
                auth_checksum = await CalculateChecksumTask(manager, auth_buf).run()
                auth_checksum = Checksum(auth_checksum)
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
            sc._auth_checksum = None
            if auth_checksum:
                sc._auth_invalid = False
        finally:
            release_evaluation_lock(locknr)
            if not self._canceled:
                taskmanager = manager.taskmanager
                ok = not sc._auth_invalid

                def func():
                    if ok != (not sc._auth_invalid):  # BUG!
                        pass
                    elif self._canceled:
                        pass
                    else:
                        sc._auth_joining = False
                        manager.structured_cell_trigger(sc, void=(not ok))

                taskmanager.add_synctask(func, (), {}, False)


def path_cleanup(value, path):
    head = path[0]
    if len(path) == 1:
        if isinstance(value, list) and isinstance(head, int):
            if head < len(value):
                value.pop(head)
                return True
            else:
                return False
        elif isinstance(value, dict):
            if head in value:
                value.pop(head)
                return True
            else:
                return False
        else:
            return True

    if isinstance(value, dict):
        in_value = head in value
    elif isinstance(value, list):
        if not isinstance(head, int):
            return True
        in_value = len(value) > head
    else:
        return True

    if not in_value:
        return False
    subvalue = value[head]
    return path_cleanup(subvalue, path[1:])


class StructuredCellJoinTask(StructuredCellTask):

    async def _run(self):
        from ...status import StatusReasonEnum

        sc = self.structured_cell
        await self.await_sc_tasks(auth=False)

        if sc._data is not sc.auth and Checksum(sc._data._checksum):
            print("{} should have been canceled!".format(sc), file=sys.stderr)

        if sc._data._void:
            print("{} should not be void!".format(sc), file=sys.stderr)
            return

        if sc._mode != SCModeEnum.FORCE_JOINING:
            for inchannel in sc.inchannels.values():
                if not Checksum(inchannel._checksum) and not inchannel._void:
                    # Refuse to join while pending.
                    return

        manager = self.manager()
        if manager is None or manager._destroyed:
            return

        locknr = await acquire_evaluation_lock(self)

        join_dict, schema, any_prelim = _build_join_dict(sc)

        checksum = None
        from_cache = False
        has_auth = None
        has_inchannel = None
        prelim = None
        if not any_prelim:
            checksum = manager.cachemanager.get_join_cache(join_dict)
            checksum = Checksum(checksum)
            if not checksum:
                checksum = database.get_structured_cell_join(join_dict)
                if checksum:
                    manager.cachemanager.set_join_cache(join_dict, checksum)
            if checksum:
                from_cache = True
                ok = True

        if not from_cache:
            local_ok = _consider_local_evaluation(join_dict)
            if not local_ok:
                remote_ok = _consider_remote_evaluation(join_dict)
                if not remote_ok:
                    # Difficult decision. Let's try a remote pseudo-transformation anyway
                    remote_ok = True
                if remote_ok:
                    checksum = await evaluate_join_transformation_remote(
                        self.structured_cell
                    )
                    checksum = Checksum(checksum)
                    if checksum:
                        from_cache = True
                        ok = True
        try:
            data_value = None  # obeys hash pattern (if there is one), i.e. is a deep structure not a raw value
            if not from_cache:
                prelim = {}
                for out_path in sc.outchannels:
                    curr_prelim = False
                    for in_path in sc.inchannels:
                        if overlap_path(in_path, out_path):
                            curr_prelim = sc.inchannels[in_path]._prelim
                            break
                    prelim[out_path] = curr_prelim
                data_value, checksum = None, None
                ok = True
                has_auth = False
                has_inchannel = False
                if manager._blocked:
                    sc._exception = "StructuredCellJoinTask: Tasks are blocked"
                    ok = False
                else:
                    if len(sc.inchannels):
                        paths = sorted(list(sc.inchannels))
                        if paths == [()] and not sc.hash_pattern:
                            # No need for auth relic cleanup, the high level handles this case already
                            checksum = sc.inchannels[()]._checksum
                            checksum = Checksum(checksum)
                            if not checksum:
                                ok = False
                        else:
                            try:
                                if not sc.no_auth:
                                    auth_checksum = sc.auth._checksum
                                    auth_checksum = Checksum(auth_checksum)
                                    if sc._auth_invalid:
                                        ok = False
                                    else:
                                        if auth_checksum:
                                            buffer = await GetBufferTask(
                                                manager, auth_checksum
                                            ).run()
                                            if buffer is None:
                                                raise CacheMissError(
                                                    auth_checksum.hex()
                                                )
                                            data_value = await DeserializeBufferTask(
                                                manager,
                                                buffer,
                                                auth_checksum,
                                                "mixed",
                                                copy=True,
                                            ).run()
                                            if data_value is not None:
                                                has_auth = True

                                            # auth relic cleanup
                                            auth_relic_cleanup = False
                                            for path in paths:
                                                if not len(path):
                                                    auth_relic_cleanup = True
                                                    data_value = None
                                                    break
                                                elif path_cleanup(data_value, path):
                                                    auth_relic_cleanup = True
                                            if auth_relic_cleanup:
                                                if data_value is None:
                                                    auth_checksum = None
                                                else:
                                                    auth_buf = await SerializeToBufferTask(
                                                        manager,
                                                        data_value,
                                                        "mixed",
                                                        use_cache=False,  # the data_value object changes all the time...
                                                    ).run()
                                                    auth_checksum = (
                                                        await CalculateChecksumTask(
                                                            manager, auth_buf
                                                        ).run()
                                                    )
                                                    auth_checksum = Checksum(
                                                        auth_checksum
                                                    )
                                                    assert auth_checksum
                                                    buffer_cache.cache_buffer(
                                                        auth_checksum, auth_buf
                                                    )
                                                manager._set_cell_checksum(
                                                    sc.auth, auth_checksum, False
                                                )
                                            # /auth relic cleanup

                                        checksum = None  # needs to be re-computed after updating with inchannels
                            except (
                                CacheMissError
                            ):  # shouldn't happen; we keep refs-to-auth!
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
                                if data_value is None:
                                    if isinstance(paths[0], int):
                                        data_value = []
                                    elif (
                                        isinstance(paths[0], (list, tuple))
                                        and len(paths[0])
                                        and isinstance(paths[0][0], int)
                                    ):
                                        data_value = []
                                    else:
                                        if sc.hash_pattern is not None:
                                            if isinstance(sc.hash_pattern, dict):
                                                for k in sc.hash_pattern:
                                                    if k.startswith("!"):
                                                        data_value = []
                                                        break
                                        if data_value is None:
                                            data_value = {}
                                assert data_value is not None
                                for path in paths:
                                    subchecksum = sc.inchannels[path]._checksum
                                    subchecksum = Checksum(subchecksum)
                                    if subchecksum:
                                        has_inchannel = True
                                        try:
                                            # - no need to buffer-cache, since the inchannel holds a ref
                                            # - the subchecksum has already the correct hash pattern (accessors make sure of this)

                                            sub_buffer = None
                                            if (
                                                sc.hash_pattern is None
                                                or access_hash_pattern(
                                                    sc.hash_pattern, path
                                                )
                                                not in ("#", "##")
                                            ):
                                                sub_buffer = await GetBufferTask(
                                                    manager, subchecksum
                                                ).run()
                                            await set_subpath_checksum(
                                                data_value,
                                                sc.hash_pattern,
                                                path,
                                                subchecksum,
                                                sub_buffer,
                                            )
                                        except CancelledError as exc:
                                            if self._canceled:
                                                raise exc from None
                                            ok = False
                                            break
                                        except CacheMissError:
                                            sc._exception = traceback.format_exc(
                                                limit=0
                                            )
                                            sc._data._status_reason = (
                                                StatusReasonEnum.INVALID
                                            )
                                            ok = False
                                            break
                                        except (TypeError, ValueError, KeyError):
                                            sc._exception = traceback.format_exc(
                                                limit=0
                                            )
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
                        checksum = Checksum(checksum)
                        if checksum:
                            try:
                                buffer = await GetBufferTask(manager, checksum).run()
                            except (
                                CacheMissError
                            ):  # should not happen: we keep refs-to-auth!
                                sc._exception = traceback.format_exc(limit=0)
                                ok = False
                            else:
                                data_value = await DeserializeBufferTask(
                                    manager, buffer, checksum, "mixed", copy=True
                                ).run()
                                if data_value is not None:
                                    has_auth = True
                        else:
                            ok = False
                if not ok:
                    data_value = None
                    checksum = None

                checksum = Checksum(checksum)
                if not checksum and data_value is not None:
                    try:
                        buf = await SerializeToBufferTask(
                            manager,
                            data_value,
                            "mixed",
                            use_cache=False,  # the data_value object changes all the time...
                        ).run()
                        checksum = await CalculateChecksumTask(manager, buf).run()
                        assert checksum
                        buffer_cache.cache_buffer(checksum, buf)
                    except CancelledError as exc:
                        if self._canceled:
                            raise exc from None
                        ok = False
                    except CacheMissError:  # shouldn't happen; checksum is fresh
                        sc._exception = traceback.format_exc(limit=0)
                        ok = False
                    except Exception:
                        sc._exception = traceback.format_exc()
                        ok = False
            if ok:
                checksum = Checksum(checksum)
                assert checksum
                if sc.buffer is not sc.auth:
                    sc.buffer._set_checksum(checksum, from_structured_cell=True)
                if (not from_cache) and schema is not None and data_value is None:
                    try:
                        buf = await GetBufferTask(manager, checksum).run()
                    except CacheMissError:  # shouldn't happen; checksum is fresh
                        sc._exception = traceback.format_exc(limit=0)
                        ok = False
                    else:
                        data_value = await DeserializeBufferTask(
                            manager, buf, checksum, "mixed", copy=False
                        ).run()

            if ok and (not from_cache) and data_value is not None:
                schema = sc.get_schema()
                if schema == {}:
                    schema = None
            if (
                ok
                and (not from_cache)
                and data_value is not None
                and schema is not None
            ):
                if sc.hash_pattern is None:
                    true_value = copy.deepcopy(data_value)
                else:
                    try:
                        # This is very expensive!!
                        mode, true_value = await get_subpath(
                            data_value, sc.hash_pattern, ()
                        )
                        assert mode == "value"
                    except Exception:
                        try:
                            # This is very very expensive!!
                            mode, true_value = await get_subpath(
                                data_value,
                                sc.hash_pattern,
                                (),
                                perform_fingertip=True,
                                manager=manager,
                            )
                            assert mode == "value"
                        except Exception:
                            sc._exception = traceback.format_exc()
                            ok = False
                if ok:
                    from silk.Silk import Silk, ValidationError

                    s = Silk(data=true_value, schema=schema)
                    try:
                        s.validate()
                    except ValidationError:
                        sc._exception = traceback.format_exc(limit=0)
                        ok = False
                    except Exception:
                        sc._exception = traceback.format_exc()
                        ok = False

            if not from_cache:
                if sc._mode != SCModeEnum.FORCE_JOINING:
                    for inchannel in sc.inchannels.values():
                        if not Checksum(inchannel._checksum) and not inchannel._void:
                            # We have become pending. Return
                            if not sc._auth_invalid:
                                sc._exception = None
                            return

            if ok:
                checksum = Checksum(checksum)
                if (not from_cache) and (has_auth or has_inchannel):
                    assert checksum
                buffer_cache.guarantee_buffer_info(
                    checksum, "mixed", sync_to_remote=False
                )
                _update_structured_cell(
                    sc,
                    checksum,
                    manager,
                    check_canceled=lambda: self._canceled,
                    prelim=prelim,
                    from_fallback=False,
                )
                if not from_cache and not any_prelim:
                    manager.cachemanager.set_join_cache(join_dict, checksum)
                for inchannel in sc.inchannels.values():
                    inchannel._save_state()
        finally:
            release_evaluation_lock(locknr)
            if not self._canceled:
                taskmanager = manager.taskmanager

                def func():
                    if self._canceled:
                        pass
                    else:
                        sc._joining = False
                        manager.structured_cell_trigger(sc, void=(not ok))

                taskmanager.add_synctask(func, (), {}, False)


from .serialize_buffer import SerializeToBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .get_buffer import GetBufferTask
from .checksum import CalculateChecksumTask
from .accessor_update import AccessorUpdateTask
from .upon_connection import UponConnectionTask
from seamless.checksum.buffer_cache import buffer_cache
from ..cancel import SCModeEnum
from ...protocol.expression import get_subpath, set_subpath_checksum
from . import acquire_evaluation_lock, release_evaluation_lock
from seamless.checksum.database_client import database
