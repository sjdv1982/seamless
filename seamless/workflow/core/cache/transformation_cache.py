# A transformation is a dictionary of semantic checksums,
#  representing the input pins, together with celltype and subcelltype
# The checksum of a transformation is the hash of the JSON buffer of this dict.
# A job consists of a transformation together with all relevant entries
#  from the semantic-to-syntactic checksum cache

from seamless import Checksum, Buffer, CacheMissError
from seamless.checksum.json import json_dumps
from seamless.checksum.buffer_remote import write_buffer

transformation_cache = None


class HardCancelError(Exception):
    def __str__(self):
        return self.__class__.__name__


from concurrent.futures import ThreadPoolExecutor
import sys


def log(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)


def clear_future_exception(future):
    # To avoid "Task exception was never retrieved" messages
    try:
        future.result()
    except asyncio.exceptions.CancelledError as exc:
        pass
    except Exception:
        pass


import datetime
import json
import ast
import functools
import asyncio
import time
import traceback
from copy import deepcopy


# Keep transformations alive for 20 secs after the last ref has expired,
#  but only if they have been running locally for at least 20 secs,
# else, keep them alive for 1 sec
TF_KEEP_ALIVE_MIN = 1.0
TF_KEEP_ALIVE_MAX = 20.0
TF_ALIVE_THRESHOLD = 20.0

import logging

logger = logging.getLogger(__name__)


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


OLD_LOG = """*************************************************
Unknown
*************************************************

This transformer was executed previously, but its log was not kept.
"""


def _write_logs_file(tf, logs, *, clear_direct_print_file=False):
    debug = tf._debug
    if debug is None:
        return
    logs_file = debug.get("logs_file")
    if logs_file is not None:
        try:
            with open(logs_file, "w") as lf:
                lf.write(logs)
        except Exception:
            pass
    if clear_direct_print_file:
        direct_print_file = debug.get("direct_print_file")
        if direct_print_file is not None:
            try:
                with open(direct_print_file, "w") as lf:
                    lf.write("< Result was retrieved from cache >\n")
            except Exception:
                pass


class RemoteTransformer:
    _debug = None
    _exception_to_clear = None

    def __init__(self, tf_checksum, peer_id):
        self.tf_checksum = tf_checksum
        self.peer_id = peer_id
        self.queue = asyncio.Queue()


class DummyTransformer:
    _status_reason = None
    _scratch = False
    _debug = None
    _exception_to_clear = None

    def __init__(self, tf_checksum):
        self.tf_checksum = Checksum(tf_checksum)
        self.progress = None
        self.prelim = None


def incref_transformation(tf_checksum: Checksum, tf_buffer, transformation):
    tf_checksum = Checksum(tf_checksum)
    buffer_cache.incref_buffer(tf_checksum, tf_buffer, persistent=False)
    for pinname in transformation:
        if pinname in (
            "__compilers__",
            "__languages__",
            "__as__",
            "__format__",
            "__meta__",
            "__code_checksum__",
        ):
            continue
        if pinname in ("__language__", "__output__"):
            continue
        if pinname == "__env__":
            sem_checksum = Checksum(transformation[pinname])
        else:
            _, _, sem_checksum = transformation[pinname]
        sem_checksum = Checksum(sem_checksum)
        if sem_checksum:
            buffer_cache.incref(sem_checksum, persistent=(pinname == "__env__"))


def tf_get_buffer(transformation):
    assert isinstance(transformation, dict)
    d = {}
    for k in transformation:
        if k in (
            "__compilers__",
            "__languages__",
            "__meta__",
            "__env__",
            "__code_checksum__",
        ):
            continue
        v = transformation[k]
        if k in ("__language__", "__output__", "__as__", "__format__"):
            d[k] = v
            continue
        if k.startswith("SPECIAL__"):
            continue
        celltype, subcelltype, checksum = v
        if isinstance(checksum, Checksum):
            checksum = checksum.value
        d[k] = celltype, subcelltype, checksum
    buffer = json_dumps(d, as_bytes=True) + b"\n"
    return buffer


def syntactic_is_semantic(celltype, subcelltype):
    return celltype not in ("cson", "yaml", "python")


async def syntactic_to_semantic(checksum: Checksum, celltype, subcelltype, codename):
    from seamless.util.source import ast_dump

    checksum = Checksum(checksum)
    if syntactic_is_semantic(celltype, subcelltype):
        return checksum

    buffer = get_buffer(checksum, remote=True)
    buffer = Buffer(buffer).value
    if buffer is None:
        raise CacheMissError(checksum.hex()) from None
    buffer_cache.cache_buffer(checksum, buffer)
    if celltype in ("cson", "yaml"):
        semantic_checksum = try_convert(
            checksum,
            celltype,
            "plain",
            buffer=buffer,
        )
    elif celltype == "python":
        value = await deserialize(buffer, checksum, "python", False)
        tree = ast.parse(value, filename=codename)
        dump = ast_dump(tree).encode()
        semantic_checksum = await Buffer(dump).get_checksum_async()
        buffer_cache.cache_buffer(semantic_checksum, dump)
        write_buffer(semantic_checksum, dump)
    else:
        raise TypeError(celltype)
    return semantic_checksum


async def run_structured_cell_join(
    structured_cell_join_checksum, *, scratch, cachemanager
):
    from ..manager.fingertipper import FingerTipper

    fingertipper = FingerTipper(
        checksum=None, cachemanager=cachemanager, recompute=True, done=set()
    )
    join_buf = await fingertipper.fingertip_upstream(structured_cell_join_checksum)
    if join_buf is None:
        return
    join_dict = json.loads(join_buf.decode())
    result_buf = await fingertipper.fingertip_join2(structured_cell_join_checksum)
    if result_buf is None:
        return None
    result = await Buffer(result_buf).get_checksum_async()
    cachemanager.set_join_cache(join_dict, result)
    buffer_cache.cache_buffer(result, result_buf)
    if not scratch:
        write_buffer(result, result_buf)
    return result


async def run_evaluate_expression(expression_dict, fingertip_mode, *, scratch, manager):
    from ..manager.fingertipper import FingerTipper
    from seamless.checksum import Expression
    from ..manager.tasks.evaluate_expression import evaluate_expression

    d = expression_dict.copy()
    d["target_subcelltype"] = None
    d["hash_pattern"] = d.get("hash_pattern")
    d["target_hash_pattern"] = d.get("target_hash_pattern")
    d["checksum"] = Checksum(d["checksum"])
    expression = Expression(**d)

    taskmanager = manager.taskmanager
    registered = False
    if expression not in taskmanager.expression_to_task:
        registered = True
        taskmanager.register_expression(expression)

    cachemanager = manager.cachemanager
    registered2 = False
    if expression not in cachemanager.expression_to_result_checksum:
        registered2 = True
        cachemanager.register_expression(expression)
    try:
        if fingertip_mode:
            fingertipper = FingerTipper(
                checksum=None, cachemanager=cachemanager, recompute=True, done=set()
            )
            result_buf = await fingertipper.fingertip_expression2(expression)
            if result_buf is None:
                return None
            result = await Buffer(result_buf).get_checksum_async()
            buffer_cache.cache_buffer(result, result_buf)
        else:
            result = await evaluate_expression(
                expression, fingertip_mode=False, manager=manager
            )
    finally:
        # if registered:
        #    taskmanager.destroy_expression(expression)
        # if registered2:
        #    cachemanager.destroy_expression(expression)

        pass
    if result is not None and database.active:
        database.set_expression(expression, result)
        result_buf = buffer_cache.get_buffer(result)
        if not scratch and result_buf is not None:
            write_buffer(result, result_buf)
    return result


class TransformationCache:
    active = True
    _blocked = False
    _blocked_local = False
    _destroyed = False
    stateless = False  # if True, don't keep transformation results after
    #  writing them to a database
    # class singletons
    known_transformations = {}
    known_transformations_rev = {}

    def __init__(self):
        self.transformations = {}  # tf-checksum-to-transformation
        self.transformation_results = {}  # tf-checksum-to-(result-checksum, prelim)
        self.transformation_results_rev = (
            {}
        )  # result-checksum-to-list-of-tf-checksums (only for non-prelim)
        self.transformation_exceptions = {}  # tf-checksum-to-exception
        self.transformation_logs = (
            {}
        )  # tf-checksum-to-stdout/stderr-logs (max 10k each)
        self.transformation_jobs = {}  # tf-checksum-to-job
        self.rev_transformation_jobs = {}  # job-to-tf-checksum
        self.job_progress = {}

        # 1:1, transformations as tf-checksums.
        # Note that tf_checksum does not exactly correspond to the serialized transformation dict,
        # (see Transformer.get_transformation_checksum)
        self.transformer_to_transformations = {}

        self.transformations_to_transformers = (
            {}
        )  # 1:list, transformations as tf-checksums

        self.remote_transformers = {}

        self.syntactic_to_semantic_checksums = (
            {}
        )  # (checksum,celltype,subcelltype)-to-checksum
        self.semantic_to_syntactic_checksums = (
            {}
        )  # (checksum,celltype,subcelltype)-to-list-of-checksums

    @staticmethod
    def syntactic_to_semantic(checksum, celltype, subcelltype, codename):
        future = asyncio.ensure_future(
            syntactic_to_semantic(checksum, celltype, subcelltype, codename)
        )
        asyncio.get_event_loop().run_until_complete(future)
        return future.result()

    def register_known_transformation(
        self, tf_checksum: Checksum, result_checksum: Checksum
    ):
        """For transformations that were launched imperatively"""
        tf_checksum = Checksum(tf_checksum)
        result_checksum = Checksum(result_checksum)
        assert result_checksum
        curr_checksum = self.known_transformations.get(tf_checksum)
        curr_checksum = Checksum(curr_checksum)
        if curr_checksum and curr_checksum == result_checksum:
            return
        self.known_transformations[tf_checksum] = result_checksum
        try:
            transformations = self.known_transformations_rev[result_checksum]
        except KeyError:
            transformations = []
            self.known_transformations_rev[result_checksum] = transformations
        transformations.append(tf_checksum)

    def register_transformer(self, transformer):
        assert isinstance(transformer, Transformer)
        assert transformer not in self.transformer_to_transformations
        self.transformer_to_transformations[transformer] = None

    def cancel_transformer(self, transformer, void_error):
        assert isinstance(transformer, Transformer)
        assert transformer in self.transformer_to_transformations
        tf_checksum = self.transformer_to_transformations.get(transformer)
        tf_checksum = Checksum(tf_checksum)
        if tf_checksum:
            transformation = self.transformations[tf_checksum]
            if not void_error:
                self.decref_transformation(transformation, transformer)
                self.transformer_to_transformations[transformer] = None

    def destroy_transformer(self, transformer):
        assert isinstance(transformer, Transformer)
        tf_checksum = self.transformer_to_transformations.pop(transformer)
        tf_checksum = Checksum(tf_checksum)
        if tf_checksum:
            transformation = self.transformations[tf_checksum]
            self.decref_transformation(transformation, transformer)

    async def build_transformation(
        self, transformer, celltypes, inputpin_checksums, outputpin
    ):
        assert isinstance(transformer, Transformer)
        cachemanager = transformer._get_manager().cachemanager
        assert isinstance(outputpin, tuple) and len(outputpin) in (3, 4)
        transformation = {"__language__": "python"}
        transformation["__output__"] = outputpin
        as_ = {}
        FORMAT = {}
        root = transformer._root()
        if root._compilers is not None:
            transformation["__compilers__"] = root._compilers
        if root._languages is not None:
            transformation["__languages__"] = root._languages
        meta = {
            "transformer_path": list(transformer.path),
        }
        if transformer.meta is not None:
            meta.update(transformer.meta)
        if "META" in inputpin_checksums:
            checksum = inputpin_checksums["META"]
            await cachemanager.fingertip(checksum)
            inp_metabuf = get_buffer(checksum, remote=True)
            if inp_metabuf is None:
                raise CacheMissError("META")
            inp_meta = json.loads(inp_metabuf)
            meta.update(inp_meta)
        transformation["__meta__"] = meta
        if transformer.env is not None:
            envbuf = await Buffer.from_async(transformer.env, "plain")
            env_checksum = await envbuf.get_checksum_async()
            buffer_cache.cache_buffer(env_checksum, envbuf)
            buffer_cache.guarantee_buffer_info(
                env_checksum, "plain", sync_to_remote=True
            )
            transformation["__env__"] = env_checksum.hex()
        transformation_build_exception = None

        for pinname, checksum in inputpin_checksums.items():
            checksum = Checksum(checksum)
            if pinname == "META":
                continue
            pin = transformer._pins[pinname]
            filesystem = pin._filesystem
            hash_pattern = pin._hash_pattern
            if filesystem is not None or hash_pattern is not None:
                FORMAT[pinname] = {}
            if filesystem is not None:
                FORMAT[pinname]["filesystem"] = deepcopy(filesystem)
            if hash_pattern is not None:
                FORMAT[pinname]["hash_pattern"] = deepcopy(hash_pattern)
            """
            # code below is only relevant for local evaluation
            # disable it for now
            try:
                await cachemanager.fingertip(checksum)
            except CacheMissError as exc:
                transformation_build_exception = exc
                break
            """

            pin = transformer._pins[pinname]
            celltype, subcelltype = celltypes[pinname]
            if pin.as_ is not None:
                as_[pinname] = pin.as_
            if not checksum:
                sem_checksum = Checksum(None)
            else:
                key = (checksum, celltype, subcelltype)
                sem_checksum = self.syntactic_to_semantic_checksums.get(key)
                sem_checksum = Checksum(sem_checksum)
                if not sem_checksum:
                    codename = str(pin)
                    if not syntactic_is_semantic(celltype, subcelltype):
                        try:
                            sem_checksum = await syntactic_to_semantic(
                                checksum, celltype, subcelltype, codename
                            )
                        except Exception as exc:
                            transformation_build_exception = exc
                            break
                        self.syntactic_to_semantic_checksums[key] = sem_checksum
                        semkey = (sem_checksum, celltype, subcelltype)
                        if semkey in self.semantic_to_syntactic_checksums:
                            semsyn = self.semantic_to_syntactic_checksums[semkey]
                        else:
                            semsyn = database.get_sem2syn(semkey)
                            if semsyn is None:
                                semsyn = []
                            self.semantic_to_syntactic_checksums[semkey] = semsyn
                        semsyn.append(checksum)
                        database.set_sem2syn(semkey, semsyn)
                    else:
                        sem_checksum = checksum
            sem_checksum = Checksum(sem_checksum)
            transformation[pinname] = celltype, subcelltype, sem_checksum
        if len(FORMAT):
            transformation["__format__"] = FORMAT
        if len(as_):
            transformation["__as__"] = as_
        return transformation, transformation_build_exception

    async def update_transformer(
        self, transformer, celltypes, inputpin_checksums, outputpin
    ):
        assert isinstance(transformer, Transformer)
        transformation, transformation_build_exception = (
            await self.build_transformation(
                transformer, celltypes, inputpin_checksums, outputpin
            )
        )
        result = await self.incref_transformation(
            transformation,
            transformer,
            transformation_build_exception=transformation_build_exception,
        )
        if result is not None:
            tf_checksum, tf_exc, result_checksum, prelim = result
            tf_checksum = Checksum(tf_checksum)
            result_checksum = Checksum(result_checksum)
            if tf_exc is None and ((not result_checksum) or prelim):
                try:
                    job = self.run_job(
                        transformation, tf_checksum, scratch=transformer._scratch
                    )
                except Exception as exc:
                    self._set_exc([transformer], tf_checksum, exc)
                    job = None
                if job is not None:
                    await asyncio.shield(job.future)
            elif tf_exc is not None:
                self._set_exc([transformer], tf_checksum, tf_exc)

    async def remote_wait(self, tf_checksum, peer_id):
        key = tf_checksum, peer_id
        transformer = self.remote_transformers.get(key)
        if transformer is None:
            return
        await transformer.queue.get()
        while 1:
            try:
                transformer.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def incref_transformation(
        self, transformation, transformer, *, transformation_build_exception
    ):
        ###import traceback; traceback.print_stack()
        assert isinstance(
            transformer, (Transformer, RemoteTransformer, DummyTransformer)
        )
        if isinstance(transformer, RemoteTransformer):
            key = transformer.tf_checksum, transformer.peer_id
            if key in self.remote_transformers:
                return
            self.remote_transformers[key] = transformer
        from ..manager.tasks.transformer_update import TransformerResultUpdateTask

        tf_buffer = tf_get_buffer(transformation)
        tf_checksum = await Buffer(tf_buffer).get_checksum_async()
        # print("INCREF", tf_checksum.hex(), transformer)

        # Force tf_buffer to be written persistently to a buffer write server
        buffer_cache.cache_buffer(tf_checksum, tf_buffer)
        buffer_cache.incref(tf_checksum, persistent=True)
        buffer_cache.decref(tf_checksum)

        if tf_checksum not in self.transformations:
            self.transformations_to_transformers[tf_checksum] = []
            self.transformations[tf_checksum] = transformation
            if tf_checksum in self.transformation_results:
                result_checksum, prelim = self.transformation_results[tf_checksum]
                buffer_cache.incref(result_checksum, persistent=False)
            incref_transformation(tf_checksum, tf_buffer, transformation)
        else:
            # Just to reflect updates in __meta__, __env__ etc.
            self.transformations[tf_checksum] = transformation

        tf = self.transformations_to_transformers[tf_checksum]
        if transformer not in tf:
            tf.append(transformer)
        if tf_checksum in self.transformation_results:
            if tf_checksum not in self.transformation_logs:
                self.transformation_logs[tf_checksum] = OLD_LOG
            for transf in tf:
                _write_logs_file(
                    transf,
                    self.transformation_logs[tf_checksum],
                    clear_direct_print_file=True,
                )

        tf_exc = self.transformation_exceptions.get(tf_checksum)

        clear_new_transformer_exceptions = True
        if isinstance(transformer, Transformer):
            clear_new_transformer_exceptions = (
                transformer._get_manager().CLEAR_NEW_TRANSFORMER_EXCEPTIONS
            )

        if clear_new_transformer_exceptions:
            if transformer._exception_to_clear or transformer._debug:
                self.clear_exception(tf_checksum=tf_checksum)
                transformer._exception_to_clear = False
                tf_exc = None

        if isinstance(transformer, (RemoteTransformer, DummyTransformer)):
            old_tf_checksum = None
        else:
            old_tf_checksum = self.transformer_to_transformations[transformer]
        old_tf_checksum = Checksum(old_tf_checksum)
        if old_tf_checksum != tf_checksum:
            if isinstance(transformer, Transformer):
                self.transformer_to_transformations[transformer] = tf_checksum
            if old_tf_checksum:
                # print("INCREF WITH OLD",  tf_checksum.hex(), old_tf_checksum.hex())
                old_transformation = self.transformations[old_tf_checksum]
                self.decref_transformation(old_transformation, transformer)

        if transformation_build_exception is not None:
            self.transformation_exceptions[tf_checksum] = transformation_build_exception
            transformers = self.transformations_to_transformers[tf_checksum]
            self._set_exc(transformers, tf_checksum, transformation_build_exception)
            return

        result_checksum, prelim = await self._get_transformation_result_async(
            tf_checksum
        )
        result_checksum = Checksum(result_checksum)
        if result_checksum:
            if isinstance(transformer, Transformer):
                # print("CACHE HIT", transformer, result_checksum.hex())
                from ...metalevel.debugmount import debugmountmanager

                if debugmountmanager.is_mounted(transformer):
                    debugmountmanager.debug_result(transformer, result_checksum)
                    return
                else:
                    manager = transformer._get_manager()
                    manager._set_transformer_checksum(
                        transformer, result_checksum, False, prelim=prelim
                    )
                    TransformerResultUpdateTask(manager, transformer).launch()
        return tf_checksum, tf_exc, result_checksum, prelim

    def decref_transformation(self, transformation, transformer):
        assert isinstance(
            transformer, (Transformer, RemoteTransformer, DummyTransformer)
        )
        if isinstance(transformer, RemoteTransformer):
            try:
                transformer.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
            key = transformer.tf_checksum, transformer.peer_id
            self.remote_transformers.pop(key, None)
        tf_buffer = tf_get_buffer(transformation)
        tf_checksum = Buffer(tf_buffer).get_checksum()
        # print("DECREF", tf_checksum.hex(), transformer, self.transformations_to_transformers.get(tf_checksum))
        assert tf_checksum in self.transformations
        if not isinstance(transformer, DummyTransformer):
            dummy = False
            transformers = self.transformations_to_transformers[tf_checksum]
            assert transformer in transformers
            transformers.remove(transformer)
        else:
            dummy = True
            try:
                transformers = self.transformations_to_transformers[tf_checksum]
                transformers.remove(transformer)
            except (KeyError, ValueError):
                pass
        if not len(transformers):
            delay = TF_KEEP_ALIVE_MIN
            job = self.transformation_jobs.get(tf_checksum)
            if (
                job is not None
                and job.start is not None
                and time.time() - job.start > TF_ALIVE_THRESHOLD
            ):
                delay = TF_KEEP_ALIVE_MAX
            tempref = functools.partial(
                self.destroy_transformation, transformation, dummy
            )
            if dummy:
                temprefmanager.add_ref(
                    tempref, delay, on_shutdown=True, group="imperative"
                )
            else:
                temprefmanager.add_ref(tempref, delay, on_shutdown=True)

    def destroy_transformation(self, transformation, dummy):
        tf_buffer = tf_get_buffer(transformation)
        tf_checksum = Buffer(tf_buffer).get_checksum()
        if not dummy:
            if tf_checksum in self.transformations_to_transformers:
                if len(self.transformations_to_transformers[tf_checksum]):
                    return  # A new transformer was registered in the meantime
            else:
                return
        if tf_checksum not in self.transformations:
            print(
                "WARNING: cannot destroy unknown transformation %s" % tf_checksum.hex()
            )
            return
        self.transformations.pop(tf_checksum)
        if not dummy:
            self.transformations_to_transformers.pop(tf_checksum)
            self.transformation_logs.pop(tf_checksum, None)
            # TODO: clear transformation_exceptions also at some moment??
        for pinname in transformation:
            if pinname in (
                "__language__",
                "__output__",
                "__languages__",
                "__compilers__",
                "__as__",
                "__format__",
                "__meta__",
                "__code_checksum__",
            ):
                continue
            if pinname == "__env__":
                checksum = Checksum(transformation[pinname])
                buffer_cache.decref(checksum)
                continue
            celltype, subcelltype, sem_checksum = transformation[pinname]
            sem_checksum = Checksum(sem_checksum)
            if sem_checksum:
                buffer_cache.decref(sem_checksum)
        buffer_cache.decref(tf_checksum)
        if tf_checksum in self.transformation_results:
            result_checksum, result_prelim = self.transformation_results[tf_checksum]
            buffer_cache.decref(result_checksum)
            if result_prelim:
                self.transformation_results.pop(tf_checksum)
        job = self.transformation_jobs.get(tf_checksum)
        if job is not None:
            if job.future is not None:
                job._cancelled = True
                if job.remote_futures is not None:
                    for fut in job.remote_futures:
                        fut.cancel()
                job.future.cancel()

    def build_semantic_cache(self, transformation):
        semantic_cache = {}
        for k, v in transformation.items():
            if k in (
                "__compilers__",
                "__languages__",
                "__meta__",
                "__format__",
                "__code_checksum__",
            ):
                continue
            if k in ("__language__", "__output__", "__as__"):
                continue
            if k == "__env__":
                continue
            celltype, subcelltype, sem_checksum = v
            sem_checksum = Checksum(sem_checksum)
            if syntactic_is_semantic(celltype, subcelltype):
                continue
            semkey = (sem_checksum, celltype, subcelltype)
            try:
                checksums = self.semantic_to_syntactic_checksums[semkey]
            except KeyError:
                semsyn = database.get_sem2syn(semkey)
                if semsyn is not None:
                    checksums = semsyn
                    self.semantic_to_syntactic_checksums[semkey] = semsyn
                else:
                    raise KeyError(sem_checksum, celltype, subcelltype) from None
            semantic_cache[semkey] = checksums
        return semantic_cache

    def run_job(self, transformation, tf_checksum, *, scratch, fingertip=False):
        if self._blocked:
            raise SeamlessTransformationError("All transformation jobs are blocked")
        transformers = self.transformations_to_transformers[tf_checksum]
        if tf_checksum in self.transformation_exceptions:
            exc = self.transformation_exceptions[tf_checksum]
            self._set_exc(transformers, tf_checksum, exc)
            return
        for transformer in self.transformations_to_transformers[tf_checksum]:
            transformer._status_reason = StatusReasonEnum.EXECUTING
        existing_job = self.transformation_jobs.get(tf_checksum)
        if existing_job is not None:
            return existing_job
        if not len(transformers):
            codename = "<Unknown>"
        else:
            last_tf = transformers[-1]
            if isinstance(last_tf, DummyTransformer):
                codename = "transformer"
            else:
                codename = str(last_tf)

        debug = None
        tfs = []
        for transformer in transformers:
            if (
                debug is None
                and hasattr(transformer, "_debug")
                and transformer._debug is not None
            ):
                debug = deepcopy(transformer._debug)
            if isinstance(transformer, (RemoteTransformer, DummyTransformer)):
                continue
            tfs.append(transformer._format_path())
        if len(tfs):
            tftxt = ",".join(tfs)
            print_info("Executing transformer: {}".format(tftxt))

        semantic_cache = self.build_semantic_cache(transformation)
        job = TransformationJob(
            tf_checksum,
            codename,
            transformation,
            semantic_cache,
            fingertip=fingertip,
            debug=debug,
            scratch=scratch,
            cannot_be_local=self._blocked_local,
        )
        job.execute(self.prelim_callback, self.progress_callback)

        self.transformation_jobs[tf_checksum] = job
        self.rev_transformation_jobs[id(job)] = tf_checksum
        return job

    def progress_callback(self, job, progress):
        self.job_progress[id(job)] = progress
        tf_checksum = self.rev_transformation_jobs[id(job)]
        transformers = self.transformations_to_transformers[tf_checksum]
        for transformer in transformers:
            if isinstance(transformer, RemoteTransformer):
                try:
                    transformer.queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
                continue
            if isinstance(transformer, DummyTransformer):
                transformer.progress = progress
                continue
            manager = transformer._get_manager()
            manager._set_transformer_progress(transformer, progress)

    def prelim_callback(self, job, prelim_checksum: Checksum):
        prelim_checksum = Checksum(prelim_checksum)
        if not prelim_checksum:
            return
        tf_checksum = self.rev_transformation_jobs[id(job)]
        transformers = self.transformations_to_transformers[tf_checksum]
        for transformer in transformers:
            if isinstance(transformer, RemoteTransformer):
                try:
                    transformer.queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            if isinstance(transformer, DummyTransformer):
                transformer.prelim = prelim_checksum
        self._set_transformation_result(
            tf_checksum, prelim_checksum, True, execution_metadata=None
        )

    def _hard_cancel(self, job):
        if self._destroyed:
            return
        future = job.future
        assert future is not None
        if future.done():
            return
        # future.set_exception(HardCancelError()) # does not work...
        job._hard_cancelled = True
        if job.remote_futures is not None:
            for fut in job.remote_futures:
                fut.cancel()
        future.cancel()

    def _set_exc(self, transformers, tf_checksum, exc):
        self.transformation_exceptions[tf_checksum] = exc
        # TODO: offload to provenance? unless hard-canceled
        if tf_checksum not in self.transformation_logs:
            if isinstance(
                exc,
                (
                    RemoteJobError,
                    SeamlessTransformationError,
                    SeamlessStreamTransformationError,
                    CacheMissError,
                ),
            ):
                logs = exc.args[0]
            else:
                s = traceback.format_exception(type(exc), exc, tb=exc.__traceback__)
                logs = "".join(s)
            self.transformation_logs[tf_checksum] = logs
        else:
            logs = self.transformation_logs[tf_checksum]

        for transformer in list(transformers):
            if isinstance(transformer, (RemoteTransformer, DummyTransformer)):
                continue

            manager = transformer._get_manager()

            if isinstance(exc, SeamlessInvalidValueError):
                status_reason = StatusReasonEnum.INVALID
            elif isinstance(exc, SeamlessUndefinedError):
                status_reason = StatusReasonEnum.UNDEFINED
            else:
                status_reason = StatusReasonEnum.ERROR
            manager.cancel_transformer(transformer, void=True, reason=status_reason)
            _write_logs_file(transformer, logs)

    def job_done(self, job: "TransformationJob", _):
        if self._destroyed:
            return

        future = job.future
        cancelled = (future.cancelled() or job._cancelled) and not job._hard_cancelled

        tf_checksum = self.rev_transformation_jobs.pop(id(job))
        tf_checksum = Checksum(tf_checksum)
        self.job_progress.pop(id(job), None)
        # print("/RUN JOB!",len(self.rev_transformation_jobs), cancelled)
        if tf_checksum in self.transformations:
            self.transformation_jobs[tf_checksum] = None
        else:
            self.transformation_jobs.pop(tf_checksum)
            return  # transformation was destroyed

        transformation = self.transformations[tf_checksum]
        transformers = self.transformations_to_transformers[tf_checksum]
        # print("DONE!", tf_checksum.hex(), transformers, cancelled)

        for transformer in list(transformers):
            if isinstance(transformer, RemoteTransformer):
                try:
                    transformer.queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
                self.decref_transformation(transformation, transformer)
            if isinstance(transformer, DummyTransformer):
                self.decref_transformation(transformation, transformer)

        if cancelled:
            return

        if job._hard_cancelled:
            exc = HardCancelError()
            print_debug("Hard cancel:", job.codename)
        else:
            exc = future.exception()
            if exc is None:
                result_checksum, logs = future.result()
                result_checksum = Checksum(result_checksum)
                self.transformation_logs[tf_checksum] = logs
                if not result_checksum:
                    exc = SeamlessUndefinedError()
            else:
                self.transformation_logs.pop(tf_checksum, None)

        if exc is not None and job.remote:
            try:
                future.result()
            except:
                pass
                """
                if not isinstance(exc, HardCancelError) and not job._hard_cancelled and not 1:
                    print("!" * 80)
                    print("!      Transformer remote exception", job.codename)
                    print("!" * 80)
                    import traceback
                    traceback.print_exc()
                    print("!" * 80)
                """

        transformers = self.transformations_to_transformers[tf_checksum]

        if exc is not None:
            if isinstance(exc, SeamlessTransformationError):
                exc_str = None
                if len(exc.args):
                    exc_str = exc.args[0]
                if exc_str is not None:
                    h = SeamlessTransformationError.__module__
                    h += "." + SeamlessTransformationError.__name__
                    if exc_str.startswith(h):
                        exc_str = exc_str[len(h) + 1 :].lstrip().rstrip("\n")
                exc = SeamlessTransformationError(exc_str)
            self.transformation_exceptions[tf_checksum] = exc
            self._set_exc(transformers, tf_checksum, exc)
        else:
            self._set_transformation_result(
                tf_checksum,
                result_checksum,
                False,
                job.execution_metadata,
                update=not job.fingertip,
            )
            logs = self.transformation_logs.get(tf_checksum)
            if logs is not None:
                for tf in transformers:
                    _write_logs_file(tf, logs)

        if database.active and not job.remote:
            meta = job.execution_metadata
            if meta is not None:
                if exc is not None:
                    meta["Success"] = False
                    meta["Exception"] = str(exc)
                    progress = self.job_progress.get(id(job))
                    if progress is not None:
                        meta["Progress"] = progress
                    if job.start is not None:
                        execution_time = time.time() - job.start
                        job.execution_metadata["Execution time (seconds)"] = (
                            execution_time
                        )
                else:
                    meta["Success"] = True
                meta["Time"] = str(datetime.datetime.now())
                database.set_metadata(tf_checksum, meta)

    def _set_transformation_result(
        self,
        tf_checksum: Checksum,
        result_checksum: Checksum,
        prelim,
        execution_metadata,
        *,
        update=True
    ):
        from ..manager.tasks.transformer_update import TransformerResultUpdateTask

        tf_checksum = Checksum(tf_checksum)
        result_checksum = Checksum(result_checksum)
        if tf_checksum in self.transformation_results:
            old_result_checksum, old_prelim = self.transformation_results[tf_checksum]
            if not old_prelim:
                return  # transformation result was already set by something else
            buffer_cache.decref(old_result_checksum)
        self.transformation_results[tf_checksum] = result_checksum, prelim
        buffer_cache.incref(result_checksum, persistent=False)
        if not prelim:
            if not self.stateless:
                if result_checksum not in self.transformation_results_rev:
                    self.transformation_results_rev[result_checksum] = []
                self.transformation_results_rev[result_checksum].append(tf_checksum)
            database.set_transformation_result(tf_checksum, result_checksum)
            if self.stateless:
                self.transformation_results.pop(tf_checksum)
        transformers = self.transformations_to_transformers[tf_checksum]
        for transformer in transformers:
            if not update:
                continue
            if isinstance(transformer, (RemoteTransformer, DummyTransformer)):
                continue
            manager = transformer._get_manager()
            if result_checksum:
                manager._set_transformer_checksum(
                    transformer, result_checksum, False, prelim=prelim
                )
                TransformerResultUpdateTask(manager, transformer).launch()
            else:
                manager.cancel_transformer(
                    transformer, void=True, reason=StatusReasonEnum.UNDEFINED
                )

    def _get_transformation_result(self, tf_checksum):
        result_checksum, prelim = self.transformation_results.get(
            tf_checksum, (None, None)
        )
        result_checksum = Checksum(result_checksum)
        if not result_checksum:
            result_checksum = database.get_transformation_result(tf_checksum)
            result_checksum = Checksum(result_checksum)
            prelim = False
            if not self.stateless and result_checksum:
                self.transformation_results[tf_checksum] = result_checksum, False
                buffer_cache.incref(result_checksum, persistent=False)
                if result_checksum not in self.transformation_results_rev:
                    self.transformation_results_rev[result_checksum] = []
                self.transformation_results_rev[result_checksum].append(tf_checksum)

        return result_checksum, prelim

    async def _get_transformation_result_async(self, tf_checksum: Checksum):
        tf_checksum = Checksum(tf_checksum)
        result_checksum, prelim = self.transformation_results.get(
            tf_checksum, (None, None)
        )
        result_checksum = Checksum(result_checksum)
        if not result_checksum:
            result_checksum = await database.get_transformation_result_async(
                tf_checksum
            )
            result_checksum = Checksum(result_checksum)
            prelim = False
            if not self.stateless and result_checksum:
                self.transformation_results[tf_checksum] = result_checksum, False
                buffer_cache.incref(result_checksum, persistent=False)
                if result_checksum not in self.transformation_results_rev:
                    self.transformation_results_rev[result_checksum] = []
                self.transformation_results_rev[result_checksum].append(tf_checksum)

        return result_checksum, prelim

    async def serve_semantic_to_syntactic(
        self, sem_checksum: Checksum, celltype, subcelltype, peer_id
    ):
        sem_checksum = Checksum(sem_checksum)

        def ret(semsyn):
            semsyn2 = []
            for semsyn_checksum in semsyn:
                if isinstance(semsyn_checksum, bytes):
                    semsyn_checksum = Checksum(semsyn_checksum)
                assert isinstance(semsyn_checksum, Checksum), semsyn
                semsyn2.append(semsyn_checksum)
            return semsyn2

        if syntactic_is_semantic(celltype, subcelltype):
            return ret([sem_checksum])
        semkey = (sem_checksum, celltype, subcelltype)
        semsyn = self.semantic_to_syntactic_checksums.get(semkey)
        if semsyn is not None:
            return ret(semsyn)
        semsyn = database.get_sem2syn(semkey)
        if semsyn is not None:
            self.semantic_to_syntactic_checksums[semkey] = semsyn
            return ret(semsyn)
        return None

    def get_transformation_dict(self, tf_checksum: Checksum) -> dict:
        """Return transformation dict corresponding to a checksum
        This transformation dict must have been previously defined
        and registered, e.g. by a transformer.
        Additional information that does not contribute to the checksum
        (__meta__, __languages__ and __compilers__) is also included.
        """
        tf_checksum = Checksum(tf_checksum)
        try:
            return self.transformations[tf_checksum]
        except KeyError:
            raise KeyError(tf_checksum) from None

    async def serve_get_transformation(self, tf_checksum: Checksum, remote_peer_id):
        tf_checksum = Checksum(tf_checksum)
        transformation = self.transformations.get(tf_checksum)
        if transformation is None:
            transformation_buffer = get_buffer(tf_checksum, remote=True)
            if transformation_buffer is not None:
                transformation = json.loads(transformation_buffer)
        return transformation

    async def serve_transformation_status(self, tf_checksum: Checksum, peer_id):
        tf_checksum = Checksum(tf_checksum)
        result_checksum, prelim = await self._get_transformation_result_async(
            tf_checksum
        )
        result_checksum = Checksum(result_checksum)
        if result_checksum:
            if not prelim:
                return 3, result_checksum
        running_job = self.transformation_jobs.get(tf_checksum)
        if running_job is not None:
            progress = self.job_progress.get(id(running_job))
            return 2, progress, result_checksum
        exc = self.transformation_exceptions.get(tf_checksum)
        if exc is not None:
            exc_list = traceback.format_exception(type(exc), exc, tb=exc.__traceback__)
            exc_str = "".join(exc_list)
            return 0, exc_str
        transformation = await self.serve_get_transformation(
            tf_checksum, remote_peer_id=peer_id
        )
        if transformation is None:
            return -3, None

        if "__hash_pattern__" in transformation:
            return -1, None

        for key, value in transformation.items():
            if key in ("__output__", "__as__", "__language__"):
                continue
            celltype, subcelltype, sem_checksum0 = value
            sem_checksum = Checksum(sem_checksum0)
            if syntactic_is_semantic(celltype, subcelltype):
                syn_checksums = [sem_checksum]
            else:
                syn_checksums = await self.serve_semantic_to_syntactic(
                    sem_checksum, celltype, subcelltype, peer_id=None
                )
                if syn_checksums is None:
                    syn_checksums = []
            for syn_checksum in syn_checksums:
                if buffer_cache.buffer_check(syn_checksum):
                    break
            else:
                return -2, None

        # Seamless instances do not accept deep transformation jobs
        # Otherwise, Seamless instances never return -1 (not runnable), although supervisors may

        return 1, None

    def clear_exception(self, transformer=None, *, tf_checksum: Checksum | None = None):
        from ..manager.tasks.transformer_update import TransformerUpdateTask
        from ..manager.unvoid import unvoid_transformer

        tf_checksum = Checksum(tf_checksum)
        if transformer is None:
            assert tf_checksum
        else:
            assert not tf_checksum
            tf_checksum = self.transformer_to_transformations.get(transformer)
            tf_checksum = Checksum(tf_checksum)
        if not tf_checksum:
            transformer._exception_to_clear = True
            return
        exc = self.transformation_exceptions.pop(tf_checksum, None)
        if exc is None:
            return
        for tf in self.transformations_to_transformers[tf_checksum]:
            if isinstance(tf, RemoteTransformer):
                key = tf.tf_checksum, tf.peer_id
                try:
                    tf.queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

                self.remote_transformers.pop(key, None)
                continue
            if isinstance(tf, DummyTransformer):
                continue
            unvoid_transformer(tf, tf._get_manager().livegraph)
            TransformerUpdateTask(tf._get_manager(), tf).launch()

    def hard_cancel(self, transformer=None, *, tf_checksum: Checksum | None = None):
        tf_checksum = Checksum(tf_checksum)
        if transformer is None:
            assert tf_checksum
        else:
            assert not tf_checksum
            tf_checksum = self.transformer_to_transformations.get(transformer)
            tf_checksum = Checksum(tf_checksum)
        if not tf_checksum:
            return
        job = self.transformation_jobs.get(tf_checksum)
        if job is None:
            return
        self._hard_cancel(job)

    async def run_transformation_async(
        self,
        tf_checksum: Checksum,
        *,
        fingertip,
        scratch,
        tf_dunder=None,
        manager=None,
        cache_only=False
    ):
        tf_checksum = Checksum(tf_checksum)
        result_checksum, prelim = await self._get_transformation_result_async(
            tf_checksum
        )
        result_checksum = Checksum(result_checksum)
        if result_checksum and not prelim:
            self.register_known_transformation(tf_checksum, result_checksum)
            if not fingertip:
                return result_checksum
        if cache_only:
            return None
        transformation = await self.serve_get_transformation(tf_checksum, None)
        if transformation is None:
            raise CacheMissError(tf_checksum.hex())
        if tf_dunder is not None:
            transformation = transformation.copy()
            for k in ("__compilers__", "__languages__", "__meta__", "__env__"):
                if k in tf_dunder:
                    transformation[k] = tf_dunder[k]
        lang = transformation.get("__language__")
        if lang == "<structured_cell_join>":
            assert manager is not None
            join_dict = transformation["structured_cell_join"]
            join_dict_buffer = await Buffer.from_async(join_dict, "plain")
            join_dict_checksum = await join_dict_buffer.get_checksum_async()
            if not join_dict_checksum:
                raise TypeError
            buffer_cache.cache_buffer(join_dict_checksum, join_dict_buffer)
            return await run_structured_cell_join(
                join_dict_checksum, cachemanager=manager.cachemanager, scratch=scratch
            )
        elif lang == "<expression>":
            assert manager is not None
            expression_dict = transformation["expression"]
            return await run_evaluate_expression(
                expression_dict,
                fingertip_mode=fingertip,
                scratch=scratch,
                manager=manager,
            )

        for k, v in transformation.items():
            if k in ("__language__", "__output__", "__as__", "__format__"):
                continue
            if k == "__env__":
                continue
            if k in ("__compilers__", "__languages__", "__meta__", "__code_checksum__"):
                continue
            celltype, subcelltype, sem_checksum0 = v
            sem_checksum = Checksum(sem_checksum0)
            if syntactic_is_semantic(celltype, subcelltype):
                continue
            await self.serve_semantic_to_syntactic(
                sem_checksum, celltype, subcelltype, None
            )
        meta = {}
        if tf_dunder:
            meta = tf_dunder.get("__meta__", {})
        transformer = DummyTransformer(tf_checksum)
        transformer._scratch = scratch
        if meta.get("__direct_print__"):
            transformer._debug = {"direct_print": True}

        async def incref_and_run():
            result = await self.incref_transformation(
                transformation, transformer, transformation_build_exception=None
            )
            if result is not None:
                tf_checksum, tf_exc, result_checksum, prelim = result
                tf_checksum = Checksum(tf_checksum)
                result_checksum = Checksum(result_checksum)
                if tf_exc is None and ((not result_checksum) or prelim or fingertip):
                    try:
                        job = self.run_job(
                            transformation,
                            tf_checksum,
                            scratch=transformer._scratch,
                            fingertip=fingertip,
                        )
                    except Exception as exc:
                        self._set_exc([transformer], tf_checksum, exc)
                        job = None
                    if job is not None:
                        await asyncio.shield(job.future)
                elif tf_exc is not None:
                    self._set_exc([transformer], tf_checksum, tf_exc)

        coro = incref_and_run()
        fut = asyncio.ensure_future(coro)
        fut.add_done_callback(clear_future_exception)
        last_result_checksum = None
        last_progress = None
        fut_done_time = None
        while 1:
            if transformer._status_reason == StatusReasonEnum.EXECUTING:
                if self.transformation_jobs.get(tf_checksum) is None:
                    # job has finished
                    break
            if (
                transformer.prelim != last_result_checksum
                or transformer.progress != last_progress
            ):
                last_progress = transformer.progress
                last_result_checksum = transformer.prelim
                last_result_checksum = Checksum(last_result_checksum)
                if not last_result_checksum:
                    log(last_progress)
                else:
                    log(last_progress, last_result_checksum.hex())

            if fut.done():
                # future is done, but the done callback has not yet been triggered
                # - tf_checksum has not been cleared from self.transformation_jobs
                # - tf_checksum is not in self.transformation_exceptions
                # If this situation lasts for more than 5 seconds, raise an exception
                if fut_done_time is None:
                    fut_done_time = time.time()
                else:
                    if time.time() - fut_done_time > 5:
                        fut.result()
                        raise Exception(
                            "Transformation finished, but didn't trigger a result or exception"
                        )

            await asyncio.sleep(0.05)
        result_checksum, prelim = await self._get_transformation_result_async(
            tf_checksum
        )
        result_checksum = Checksum(result_checksum)
        if tf_checksum in self.transformation_exceptions:
            raise self.transformation_exceptions[tf_checksum]

        assert not prelim
        if not result_checksum:
            raise Exception(
                "Transformation finished, but didn't trigger a result or exception"
            )

        self.register_known_transformation(tf_checksum, result_checksum)
        return result_checksum

    def run_transformation(
        self,
        tf_checksum,
        *,
        fingertip,
        scratch,
        tf_dunder=None,
        new_event_loop=False,
        manager=None
    ):
        event_loop = asyncio.get_event_loop()
        if event_loop.is_running() or new_event_loop:
            # To support run_transformation inside transformer code
            if event_loop.is_running():
                # This is potentially tricky.
                # The Seamless manager will be running in a different thread.
                # Therefore, we can't update the Seamless workflow graph, but we shouldn't have to
                # The use case is essentially: using the functional style under Jupyter
                def func():
                    coro = self.run_transformation_async(
                        tf_checksum,
                        fingertip=fingertip,
                        scratch=scratch,
                        tf_dunder=tf_dunder,
                        manager=manager,
                    )
                    # The following hangs, even for a "dummy" coroutine:
                    #  future = asyncio.run_coroutine_threadsafe(coro, event_loop)
                    #  return future.result()
                    return asyncio.run(coro)

                with ThreadPoolExecutor() as tp:
                    return tp.submit(func).result()

            else:
                loop = asyncio.new_event_loop()

                async def stop_loop(timeout):
                    loop.stop()
                    t = time.time()
                    while 1:
                        for task in asyncio.all_tasks(loop):
                            if not task.done():
                                break
                        else:
                            break
                        if time.time() - t > timeout:
                            break
                        await asyncio.sleep(0.01)

                try:
                    return loop.run_until_complete(
                        self.run_transformation_async(
                            tf_checksum,
                            fingertip=fingertip,
                            scratch=scratch,
                            tf_dunder=tf_dunder,
                            manager=manager,
                        )
                    )
                finally:
                    for task in asyncio.all_tasks(loop):
                        task.cancel()
                    asyncio.ensure_future(stop_loop(2))

        else:
            fut = asyncio.ensure_future(
                self.run_transformation_async(
                    tf_checksum,
                    fingertip=fingertip,
                    scratch=scratch,
                    tf_dunder=tf_dunder,
                    manager=manager,
                )
            )
            asyncio.get_event_loop().run_until_complete(fut)
            return fut.result()

    def undo(self, transformation_checksum: Checksum):
        """Contests a previously calculated transformation result"""
        transformation_checksum = Checksum(transformation_checksum)
        if not transformation_checksum:
            raise ValueError("transformation_checksum")

        result_checksum, _ = self._get_transformation_result(transformation_checksum)
        result_checksum = Checksum(result_checksum)
        result_checksum2 = self.known_transformations.pop(transformation_checksum, None)
        result_checksum2 = Checksum(result_checksum2)
        assert (
            not result_checksum
            or not result_checksum2
            or (result_checksum == result_checksum2)
        )

        """
        # Below will not work, but now we have a cache miss instead
        #  
        if transformation_checksum in self.transformations:
            transformation = self.transformations[transformation_checksum]
            self.destroy_transformation(transformation, dummy=True)
        """
        if transformation_checksum in self.transformation_results:
            self.transformation_results.pop(transformation_checksum, None)
        self.transformation_logs.pop(transformation_checksum, None)

        if result_checksum2:
            self.known_transformations_rev[result_checksum2].remove(
                transformation_checksum
            )
            result_checksum = result_checksum2

        if not result_checksum:
            raise RuntimeError("Unknown transformation result")
        status, response = database.contest(transformation_checksum, result_checksum)
        if status == 200:
            return result_checksum
        else:
            return response

    def destroy(self):
        # only called when Seamless shuts down
        a = self.transformer_to_transformations
        if a:
            log(
                "TransformationCache, transformer_to_transformations: %d undestroyed"
                % len(a)
            )
        for _tf_checksum, job in self.transformation_jobs.items():
            if job is None:
                continue
            future = job.future
            if future is None:
                continue
            try:
                future.cancel()
            except:
                pass


transformation_cache = TransformationCache()

from seamless.workflow.tempref import temprefmanager
from seamless.checksum.buffer_cache import buffer_cache
from seamless.checksum.get_buffer import get_buffer
from seamless.checksum.deserialize import deserialize
from seamless.checksum.database_client import database
from ..transformation import (
    TransformationJob,
    SeamlessTransformationError,
    SeamlessStreamTransformationError,
    RemoteJobError,
)
from ..status import SeamlessInvalidValueError, SeamlessUndefinedError, StatusReasonEnum
from ..transformer import Transformer
from seamless.checksum.convert import try_convert
from seamless.checksum.serialize import serialize
