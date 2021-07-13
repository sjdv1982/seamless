# A transformation is a dictionary of semantic checksums,
#  representing the input pins, together with celltype and subcelltype
# The checksum of a transformation is the hash of the JSON buffer of this dict.
# A job consists of a transformation together with all relevant entries
#  from the semantic-to-syntactic checksum cache

class HardCancelError(Exception):
    def __str__(self):
        return self.__class__.__name__

from seamless.core.protocol.serialize import serialize
import sys
def log(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)

import json
import ast
import functools
import asyncio
import time
import traceback
from copy import deepcopy

from ...get_hash import get_dict_hash, get_hash
"""
TODO: offload exceptions (as text) to database (also allow them to be cleared in database?)
TODO: do the same with stdout, stderr
TODO: add some metadata to the above? (when and where it was executed)
"""

# Keep transformations alive for 20 secs after the last ref has expired,
#  but only if they have been running locally for at least 20 secs,
# else, keep them alive for 1 sec
TF_KEEP_ALIVE_MIN = 1.0
TF_KEEP_ALIVE_MAX = 20.0
TF_ALIVE_THRESHOLD = 20.0

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

class RemoteTransformer:
    debug = None
    _exception_to_clear = None
    def __init__(self, tf_checksum, peer_id):
        self.tf_checksum = tf_checksum
        self.peer_id = peer_id
        self.queue = asyncio.Queue()

class DummyTransformer:
    _status_reason = None
    debug = None
    _exception_to_clear = None
    def __init__(self, tf_checksum):
        self.tf_checksum = tf_checksum
        self.progress = None
        self.prelim = None

def tf_get_buffer(transformation):
    assert isinstance(transformation, dict)
    d = {}
    for k in transformation:
        if k in ("__compilers__", "__languages__", "__meta__"):
            continue
        v = transformation[k]
        if k in ("__output__", "__as__"):
            d[k] = v
            continue
        elif k == "__env__":
            checksum = v
            checksum = checksum.hex()
            d[k] = checksum
            continue
        celltype, subcelltype, checksum = v
        checksum = checksum.hex()
        d[k] = celltype, subcelltype, checksum
    content = json.dumps(d, sort_keys=True, indent=2) + "\n"
    buffer = content.encode()
    return buffer


def syntactic_is_semantic(celltype, subcelltype):
    return celltype not in ("cson", "yaml", "python")

async def syntactic_to_semantic(
    checksum, celltype, subcelltype, codename
):
    assert checksum is None or isinstance(checksum, bytes)
    if syntactic_is_semantic(celltype, subcelltype):
        return checksum

    try:
        buffer = get_buffer(checksum)
    except CacheMissError:
        buffer = await get_buffer_remote(
            checksum,
            None
        )
        if buffer is None:
            raise CacheMissError(checksum.hex()) from None
        buffer_cache.cache_buffer(checksum, buffer)
    if celltype in ("cson", "yaml"):
        semantic_checksum = await convert(
            checksum, buffer, celltype, "plain"
        )
    elif celltype == "python":
        value = await deserialize(buffer, checksum, "python", False)
        tree = ast.parse(value, filename=codename)
        dump = ast.dump(tree).encode()
        semantic_checksum = await calculate_checksum(dump)
        buffer_cache.cache_buffer(semantic_checksum, dump)
    else:
        raise TypeError(celltype)
    return semantic_checksum

class TransformationCache:
    active = True
    _destroyed = False
    def __init__(self):
        self.transformations = {} # tf-checksum-to-transformation
        self.transformation_results = {} # tf-checksum-to-(result-checksum, prelim)
        self.transformation_exceptions = {} # tf-checksum-to-exception
        self.transformation_logs = {} # tf-checksum-to-stdout/stderr-logs (max 10k each)
        self.transformation_jobs = {} # tf-checksum-to-job
        self.rev_transformation_jobs = {} # job-to-tf-checksum
        self.job_progress = {}

        self.transformer_to_transformations = {} # 1:1, transformations as tf-checksums
        self.transformations_to_transformers = {} # 1:list, transformations as tf-checksums

        self.remote_transformers = {}

        self.syntactic_to_semantic_checksums = {} #(checksum,celltype,subcelltype)-to-checksum
        self.semantic_to_syntactic_checksums = {} #(checksum,celltype,subcelltype)-to-list-of-checksums

    @staticmethod
    def syntactic_to_semantic(
        checksum, celltype, subcelltype, codename
    ):
        future = asyncio.ensure_future(
            syntactic_to_semantic(
                checksum, celltype, subcelltype, codename
            )
        )
        asyncio.get_event_loop().run_until_complete(future)
        return future.result()

    def register_transformer(self, transformer):
        assert isinstance(transformer, Transformer)
        assert transformer not in self.transformer_to_transformations
        self.transformer_to_transformations[transformer] = None

    def cancel_transformer(self, transformer, void_error):
        assert isinstance(transformer, Transformer)
        assert transformer in self.transformer_to_transformations
        tf_checksum = self.transformer_to_transformations.get(transformer)
        if tf_checksum is not None:
            transformation = self.transformations[tf_checksum]
            if not void_error:
                self.decref_transformation(transformation, transformer)
                self.transformer_to_transformations[transformer] = None

    def destroy_transformer(self, transformer):
        assert isinstance(transformer, Transformer)
        tf_checksum = self.transformer_to_transformations.pop(transformer)
        if tf_checksum is not None:
            transformation = self.transformations[tf_checksum]
            self.decref_transformation(transformation, transformer)

    async def build_transformation(self, transformer, celltypes, inputpin_checksums, outputpin):
        assert isinstance(transformer, Transformer)
        cachemanager = transformer._get_manager().cachemanager
        outputname, celltype, subcelltype = outputpin
        transformation = {"__output__": outputpin}
        as_ = {}
        root = transformer._root()
        if root._compilers is not None:
            transformation["__compilers__"] = root._compilers
        if root._languages is not None:
            transformation["__languages__"] = root._languages
        meta = {
            "transformer_path": transformer.path,
        }
        if transformer.meta is not None:
            meta.update(transformer.meta)
        if "META" in inputpin_checksums:
            checksum = inputpin_checksums["META"]
            await cachemanager.fingertip(checksum)
            inp_metabuf = buffer_cache.get_buffer(checksum)
            if inp_metabuf is None:
                raise CacheMissError("META")
            inp_meta = json.loads(inp_metabuf)
            meta.update(inp_meta)
        metabuf = await serialize(meta, "plain")
        meta_checksum = get_hash(metabuf)
        buffer_cache.cache_buffer(meta_checksum, metabuf)
        transformation["__meta__"] = meta_checksum
        if transformer.env is not None:
            envbuf = await serialize(transformer.env, "plain")
            env_checksum = get_hash(envbuf)
            buffer_cache.cache_buffer(env_checksum, envbuf)
            transformation["__env__"] = env_checksum
        transformation_build_exception = None
        for pinname, checksum in inputpin_checksums.items():
            if pinname == "META":
                continue
            await cachemanager.fingertip(checksum)
            pin = transformer._pins[pinname]
            celltype, subcelltype = celltypes[pinname]
            if pin.as_ is not None:
                as_[pinname] = pin.as_
            if checksum is None:
                sem_checksum = None
            else:
                key = (checksum, celltype, subcelltype)
                sem_checksum = self.syntactic_to_semantic_checksums.get(key)
                if sem_checksum is None:
                    codename = str(pin)
                    if not syntactic_is_semantic(celltype, subcelltype):
                        try:
                            sem_checksum = await syntactic_to_semantic(
                                checksum, celltype, subcelltype,
                                codename
                            )
                        except Exception as exc:
                            transformation_build_exception = exc
                            break
                        self.syntactic_to_semantic_checksums[key] = sem_checksum
                        semkey = (sem_checksum, celltype, subcelltype)
                        if semkey in self.semantic_to_syntactic_checksums:
                            semsyn = self.semantic_to_syntactic_checksums[semkey]
                        else:
                            semsyn = database_cache.sem2syn(semkey)
                            if semsyn is None:
                                semsyn = []
                            self.semantic_to_syntactic_checksums[semkey] = semsyn
                        semsyn.append(checksum)
                        database_sink.sem2syn(semkey, semsyn)
                    else:
                        sem_checksum = checksum
            transformation[pinname] = celltype, subcelltype, sem_checksum
        if len(as_):
            transformation["__as__"] = as_
        return transformation, transformation_build_exception

    async def update_transformer(self,
        transformer, celltypes, inputpin_checksums, outputpin
    ):
        assert isinstance(transformer, Transformer)
        transformation, transformation_build_exception = \
            await self.build_transformation(                
                transformer, celltypes, inputpin_checksums, outputpin
            )
        result = await self.incref_transformation(
            transformation, transformer,
            transformation_build_exception=transformation_build_exception
        )
        if result is not None:
            tf_checksum, result_checksum, prelim = result
            if result_checksum is None or prelim:
                job = self.run_job(transformation, tf_checksum)
                if job is not None:
                    await asyncio.shield(job.future)


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


    async def incref_transformation(self, transformation, transformer, *, transformation_build_exception):
        ###import traceback; traceback.print_stack()
        assert isinstance(transformer, (Transformer, RemoteTransformer, DummyTransformer))
        if isinstance(transformer, RemoteTransformer):
            key = transformer.tf_checksum, transformer.peer_id
            if key in self.remote_transformers:
                return
            self.remote_transformers[key] = transformer
        from ..manager.tasks.transformer_update import TransformerResultUpdateTask
        tf_buffer = tf_get_buffer(transformation)
        tf_checksum = await calculate_checksum(tf_buffer)
        #print("INCREF", tf_checksum.hex(), transformer)

        if tf_checksum not in self.transformations:
            tf = []
            buffer_cache.incref_buffer(tf_checksum, tf_buffer, False)
            self.transformations_to_transformers[tf_checksum] = tf
            self.transformations[tf_checksum] = transformation
            if tf_checksum in self.transformation_results:
                result_checksum, prelim = self.transformation_results[tf_checksum]
                buffer_cache.incref(result_checksum, False)
            for pinname in transformation:
                if pinname in ("__compilers__", "__languages__", "__as__", "__meta__"):
                    continue
                if pinname == "__output__":
                    continue
                if pinname == "__env__":
                    sem_checksum = transformation[pinname]
                else:
                    celltype, subcelltype, sem_checksum = transformation[pinname]
                buffer_cache.incref(sem_checksum, (pinname == "__env__"))
        else:
            tf = self.transformations_to_transformers[tf_checksum]

        if transformer.debug is not None:
            self.clear_exception(transformer)
        if transformer._exception_to_clear:
            self.clear_exception(tf_checksum=tf_checksum)
            transformer._exception_to_clear = False

        if isinstance(transformer, (RemoteTransformer, DummyTransformer)):
            old_tf_checksum = None
        else:
            old_tf_checksum = self.transformer_to_transformations[transformer]
        if old_tf_checksum != tf_checksum:
            if isinstance(transformer, Transformer):
                self.transformer_to_transformations[transformer] = tf_checksum
            tf.append(transformer)
            if old_tf_checksum is not None:
                #print("INCREF WITH OLD",  tf_checksum.hex(), old_tf_checksum.hex())
                old_transformation = self.transformations[old_tf_checksum]
                self.decref_transformation(old_transformation, transformer)
        
        if transformation_build_exception is not None:
            self.transformation_exceptions[tf_checksum] = transformation_build_exception
            transformers = self.transformations_to_transformers[tf_checksum]
            self._set_exc(transformers, transformation_build_exception)
            return
            
        result_checksum, prelim = self._get_transformation_result(tf_checksum)
        if result_checksum is not None:
            if isinstance(transformer, Transformer):
                #print("CACHE HIT", transformer, result_checksum.hex())
                manager = transformer._get_manager()
                manager._set_transformer_checksum(
                    transformer,
                    result_checksum,
                    False,
                    prelim=prelim
                )
                TransformerResultUpdateTask(manager, transformer).launch()
        return tf_checksum, result_checksum, prelim

    def decref_transformation(self, transformation, transformer):
        ###import traceback; traceback.print_stack()
        assert isinstance(transformer, (Transformer, RemoteTransformer, DummyTransformer))
        if isinstance(transformer, RemoteTransformer):
            try:
                transformer.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
            key = transformer.tf_checksum, transformer.peer_id
            self.remote_transformers.pop(key, None)
        tf_buffer = tf_get_buffer(transformation)
        tf_checksum = calculate_checksum_sync(tf_buffer)
        #print("DECREF", tf_checksum.hex(), transformer)
        assert tf_checksum in self.transformations
        if not isinstance(transformer, DummyTransformer):
            dummy = False
            transformers = self.transformations_to_transformers[tf_checksum]
            assert transformer in transformers
            transformers.remove(transformer)
        else:
            dummy = True
            transformers = []
        if not len(transformers):
            delay = TF_KEEP_ALIVE_MIN
            job = self.transformation_jobs.get(tf_checksum)
            if job is not None and job.start is not None and \
              time.time() - job.start > TF_ALIVE_THRESHOLD:
                delay = TF_KEEP_ALIVE_MAX
            tempref = functools.partial(self.destroy_transformation, transformation, dummy)
            temprefmanager.add_ref(tempref, delay, on_shutdown=True)

    def destroy_transformation(self, transformation, dummy):
        tf_buffer = tf_get_buffer(transformation)
        tf_checksum = calculate_checksum_sync(tf_buffer)
        if not dummy:
            if tf_checksum in self.transformations_to_transformers:
                if len(self.transformations_to_transformers[tf_checksum]):
                    return # A new transformer was registered in the meantime
            else:
                return
        if tf_checksum not in self.transformations:
            print("WARNING: cannot destroy unknown transformation %s" % tf_checksum.hex())
            return
        self.transformations.pop(tf_checksum)
        if not dummy:
            self.transformations_to_transformers.pop(tf_checksum)
        for pinname in transformation:
            if pinname in ("__output__", "__languages__", "__compilers__", "__as__", "__meta__"):
                continue
            if pinname == "__env__":
                env_checksum = transformation["__env__"]
                buffer_cache.decref(env_checksum)
                continue
            celltype, subcelltype, sem_checksum = transformation[pinname]
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

    def run_job(self, transformation, tf_checksum):
        transformers = self.transformations_to_transformers[tf_checksum]
        if tf_checksum in self.transformation_exceptions:
            exc = self.transformation_exceptions[tf_checksum]
            self._set_exc(transformers, exc)
            return
        for transformer in self.transformations_to_transformers[tf_checksum]:
            transformer._status_reason = StatusReasonEnum.EXECUTING
        existing_job = self.transformation_jobs.get(tf_checksum)
        if existing_job is not None:
            return existing_job
        if not len(transformers):
            codename = "<Unknown>"
        else:
            codename = str(transformers[-1])

        debug = None
        tfs = []
        for transformer in transformers:
            if isinstance(transformer,
            (RemoteTransformer, DummyTransformer)
            ):
                continue
            tfs.append(transformer._format_path())
            if debug is None and transformer.debug is not None:
                debug = deepcopy(transformer.debug)
        if len(tfs):
            tftxt = ",".join(tfs)
            print_info("Executing transformer: {}".format(tftxt))

        semantic_cache = {}
        for k,v in transformation.items():
            if k in ("__compilers__", "__languages__", "__meta__"):
                continue
            if k in ("__output__", "__as__"):
                continue
            if k == "__env__":
                continue
            celltype, subcelltype, sem_checksum = v
            if syntactic_is_semantic(celltype, subcelltype):
                continue
            semkey = (sem_checksum, celltype, subcelltype)
            try:
                checksums = self.semantic_to_syntactic_checksums[semkey]
            except KeyError:
                raise KeyError(sem_checksum.hex(), celltype, subcelltype) from None
            semantic_cache[semkey] = checksums
        job = TransformationJob(
            tf_checksum, codename,
            transformation, semantic_cache,
            debug=debug
        )
        job.execute(
            self.prelim_callback,
            self.progress_callback
        )

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
            manager._set_transformer_progress(
                transformer,
                progress
            )

    def prelim_callback(self, job, prelim_checksum):
        if prelim_checksum is None:
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
        self.set_transformation_result(tf_checksum, prelim_checksum, True)

    def _hard_cancel(self, job):
        if self._destroyed:
            return
        future = job.future
        assert future is not None
        if future.done():
            return
        #future.set_exception(HardCancelError()) # does not work...
        job._hard_cancelled = True
        if job.remote_futures is not None:
            for fut in job.remote_futures:
                fut.cancel()
        future.cancel()

    def _set_exc(self, transformers, exc):
        # TODO: offload to provenance? unless hard-canceled
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
            manager.cancel_transformer(
                transformer,
                void=True,
                reason=status_reason
            )

    def job_done(self, job, _):
        if self._destroyed:
            return

        future = job.future
        cancelled = (future.cancelled() or job._cancelled) and not job._hard_cancelled

        tf_checksum = self.rev_transformation_jobs.pop(id(job))
        self.job_progress.pop(id(job), None)
        #print("/RUN JOB!",len(self.rev_transformation_jobs), cancelled)
        if tf_checksum in self.transformations:
            self.transformation_jobs[tf_checksum] = None
        else:
            self.transformation_jobs.pop(tf_checksum)
            return  # transformation was destroyed

        transformation = self.transformations[tf_checksum]
        transformers = self.transformations_to_transformers[tf_checksum]
        #print("DONE!", tf_checksum.hex(), transformers, cancelled)

        for transformer in list(transformers):
            if isinstance(transformer,RemoteTransformer):
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
                self.transformation_logs[tf_checksum] = logs
                if result_checksum is None:
                    exc = SeamlessUndefinedError()

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
            if isinstance(exc,SeamlessTransformationError):
                exc_str = None
                if len(exc.args):
                    exc_str = exc.args[0]
                if exc_str is not None:
                    h = SeamlessTransformationError.__module__
                    h += "." + SeamlessTransformationError.__name__
                    if exc_str.startswith(h):
                        exc_str = exc_str[len(h)+1:].lstrip().rstrip("\n")
                exc = SeamlessTransformationError(exc_str)
            self.transformation_exceptions[tf_checksum] = exc
            self._set_exc(transformers, exc)
            return
        self.set_transformation_result(tf_checksum, result_checksum, False)

    def set_transformation_result(self, tf_checksum, result_checksum, prelim):
        from ..manager.tasks.transformer_update import (
            TransformerResultUpdateTask
        )
        if tf_checksum in self.transformation_results:
            old_result_checksum, old_prelim = self.transformation_results[tf_checksum]
            if not old_prelim:
                return  # transformation result was already set by something else
            buffer_cache.decref(old_result_checksum)
        self.transformation_results[tf_checksum] = result_checksum, prelim
        buffer_cache.incref(result_checksum, False)
        if not prelim:
            database_sink.set_transformation_result(tf_checksum, result_checksum)
        transformers = self.transformations_to_transformers[tf_checksum]
        for transformer in transformers:
            if isinstance(transformer, (RemoteTransformer, DummyTransformer)):
                continue
            manager = transformer._get_manager()
            if result_checksum is not None:
                manager._set_transformer_checksum(
                    transformer,
                    result_checksum,
                    False,
                    prelim=prelim
                )
                TransformerResultUpdateTask(manager, transformer).launch()
            else:
                manager.cancel_transformer(
                    transformer,
                    void=True,
                    reason=StatusReasonEnum.UNDEFINED
                )

    def _get_transformation_result(self, tf_checksum):
        result_checksum, prelim = self.transformation_results.get(
            tf_checksum, (None, None)
        )
        if result_checksum is None:
            result_checksum = database_cache.get_transformation_result(tf_checksum)
            prelim = False
        return result_checksum, prelim

    async def serve_semantic_to_syntactic(self, sem_checksum, celltype, subcelltype, peer_id):
        from ...communion_client import communion_client_manager
        def ret(semsyn):
            for semsyn_checksum in semsyn:
                assert isinstance(semsyn_checksum, bytes), semsyn
            return semsyn
        if syntactic_is_semantic(celltype, subcelltype):
            return ret([sem_checksum])
        semkey = (sem_checksum, celltype, subcelltype)
        semsyn = self.semantic_to_syntactic_checksums.get(semkey)
        if semsyn is not None:
            return ret(semsyn)
        semsyn = database_cache.sem2syn(semkey)
        if semsyn is not None:
            self.semantic_to_syntactic_checksums[semkey] = semsyn
            return ret(semsyn)
        remote = communion_client_manager.remote_semantic_to_syntactic
        semsyn = await remote(sem_checksum, celltype, subcelltype, peer_id)
        if semsyn is not None:
            self.semantic_to_syntactic_checksums[semkey] = semsyn
            database_sink.sem2syn(semkey, semsyn)
            return ret(semsyn)
        return None

    async def serve_get_transformation(self, tf_checksum, remote_peer_id):
        assert isinstance(tf_checksum, bytes)
        transformation = self.transformations.get(tf_checksum)
        if transformation is None:
            try:
                transformation_buffer = get_buffer(
                    tf_checksum
                )
            except CacheMissError:
                transformation_buffer = await get_buffer_remote(
                    tf_checksum,
                    None # NOT remote_peer_id! The submitting peer may hold a buffer we need!
                )
            if transformation_buffer is not None:
                transformation = json.loads(transformation_buffer)
                for k,v in transformation.items():
                    if k == "__env__":
                        transformation[k] = bytes.fromhex(v)
                    elif k not in ("__output__", "__as__"):
                        if v[-1] is not None:
                            v[-1] = bytes.fromhex(v[-1])
        return transformation

    async def serve_transformation_status(self, tf_checksum, peer_id):
        assert isinstance(tf_checksum, bytes)
        from ...communion_client import communion_client_manager
        result_checksum, prelim = self._get_transformation_result(tf_checksum)
        if result_checksum is not None:
            if not prelim:
                return 3, result_checksum
        running_job = self.transformation_jobs.get(tf_checksum)
        if running_job is not None:
            progress = self.job_progress.get(id(running_job))
            return 2, progress, result_checksum
        exc = self.transformation_exceptions.get(tf_checksum)
        if exc is not None:
            exc_list = traceback.format_exception(
                value=exc,
                etype=type(exc),
                tb=exc.__traceback__
            )
            exc_str = "".join(exc_list)
            return 0, exc_str
        result = await communion_client_manager.remote_transformation_status(
            tf_checksum, peer_id
        )
        if result is not None:
            return result
        transformation = await self.serve_get_transformation(
            tf_checksum,
            remote_peer_id=peer_id
        )
        if transformation is None:
            return -3, None

        if "__hash_pattern__" in transformation:
            return -1, None

        remote = communion_client_manager.remote_buffer_status
        for key, value in transformation.items():
            if key in ("__output__", "__as__"):
                continue
            celltype, subcelltype, sem_checksum = value
            if syntactic_is_semantic(celltype, subcelltype):
                syn_checksums = [sem_checksum]
            else:
                syn_checksums = await self.serve_semantic_to_syntactic(
                    sem_checksum, celltype, subcelltype,
                    peer_id = None
                )
                if syn_checksums is None:
                    syn_checksums = []
            for syn_checksum in syn_checksums:
                if buffer_cache.buffer_check(syn_checksum):
                    break
                curr_sub_result = await remote(
                    syn_checksum, peer_id=None
                )
                if curr_sub_result:
                    break
            else:
                return -2, None

        # Seamless instances do not accept deep transformation jobs
        # Otherwise, Seamless instances never return -1 (not runnable), although supervisors may

        return 1, None

    def clear_exception(self, transformer=None, *, tf_checksum=None):
        from ..manager.tasks.transformer_update import TransformerUpdateTask
        from ...communion_client import communion_client_manager
        from ..manager.unvoid import unvoid_transformer
        if transformer is None:
            assert tf_checksum is not None
        else:
            assert tf_checksum is None
            tf_checksum = self.transformer_to_transformations.get(transformer)
        if tf_checksum is None:
            transformer._exception_to_clear = True
            return
        exc = self.transformation_exceptions.pop(tf_checksum, None)
        if exc is None:
            return
        clients = communion_client_manager.clients["transformation"]
        for client in clients:
            coro = client.clear_exception(tf_checksum)
            fut = asyncio.ensure_future(coro)
            client.future_clear_exception = fut
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

    def hard_cancel(self, transformer=None, *, tf_checksum=None):
        if transformer is None:
            assert tf_checksum is not None
        else:
            assert tf_checksum is None
            tf_checksum = self.transformer_to_transformations.get(transformer)
        if tf_checksum is None:
            return
        job = self.transformation_jobs.get(tf_checksum)
        if job is None:
            return
        self._hard_cancel(job)

    async def run_transformation_async(self, tf_checksum):
        from . import CacheMissError
        result_checksum, prelim = self._get_transformation_result(tf_checksum)
        if result_checksum is not None and not prelim:
            return result_checksum
        transformation = await self.serve_get_transformation(tf_checksum, None)
        if transformation is None:
            raise CacheMissError
        for k,v in transformation.items():
            if k in ("__output__", "__as__"):
                continue
            if k == "__env__":
                continue
            celltype, subcelltype, sem_checksum = v
            if syntactic_is_semantic(celltype, subcelltype):
                continue
            await self.serve_semantic_to_syntactic(
                sem_checksum, celltype, subcelltype,
                None
            )
        transformer = DummyTransformer(tf_checksum)
        async def incref_and_run():
            result = await self.incref_transformation(
                transformation, transformer, 
                transformation_build_exception=None 
            )
            if result is not None:
                tf_checksum, result_checksum, prelim = result
                if result_checksum is None or prelim:
                    job = self.run_job(transformation, tf_checksum)
                    if job is not None:
                        await asyncio.shield(job.future)
        coro = incref_and_run()
        fut = asyncio.ensure_future(coro)
        last_result_checksum = None
        last_progress = None
        fut_done_time = None
        while 1:
            if fut.done():
                if fut_done_time is None:
                    fut_done_time = time.time()
                else:
                    if time.time() - fut_done_time > 2:
                        fut.result()
                        raise Exception("Transformation finished, but didn't trigger a result or exception")
            if transformer._status_reason == StatusReasonEnum.EXECUTING:
                if self.transformation_jobs.get(tf_checksum) is None:
                    break
            if transformer.prelim != last_result_checksum \
              or transformer.progress != last_progress:
                last_progress = transformer.progress
                last_result_checksum = transformer.prelim
                if last_result_checksum is None:
                    log(last_progress)
                else:
                    log(last_progress, last_result_checksum.hex())
            await asyncio.sleep(0.05)
        if tf_checksum in self.transformation_exceptions:
            raise self.transformation_exceptions[tf_checksum]
        result_checksum, prelim = self._get_transformation_result(tf_checksum)
        assert not prelim
        return result_checksum

    def run_transformation(self, tf_checksum):
        fut = asyncio.ensure_future(self.run_transformation_async(tf_checksum))
        asyncio.get_event_loop().run_until_complete(fut)
        return fut.result()

    def destroy(self):
        # only called when Seamless shuts down
        a = self.transformer_to_transformations
        if a:
            log("TransformationCache, transformer_to_transformations: %d undestroyed"  % len(a))
        for tf_checksum, job in self.transformation_jobs.items():
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

from .tempref import temprefmanager
from .buffer_cache import buffer_cache
from ..protocol.get_buffer import get_buffer, get_buffer_remote, CacheMissError
from ..protocol.conversion import convert
from ..protocol.deserialize import deserialize
from ..protocol.calculate_checksum import calculate_checksum, calculate_checksum_sync
from .database_client import database_cache, database_sink
from ..transformation import TransformationJob, SeamlessTransformationError
from ..status import SeamlessInvalidValueError, SeamlessUndefinedError, StatusReasonEnum
from ..transformer import Transformer