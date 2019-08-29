# A transformation is a dictionary of semantic checksums, 
#  representing the input pins, together with celltype and subcelltype
# The checksum of a transformation is the hash of the JSON buffer of this dict.
# A job consists of a transformation together with all relevant entries 
#  from the semantic-to-syntactic checksum cache

class HardCancelError(Exception):
    def __str__(self):
        return self.__class__.__name__

import json
import ast
import functools
import asyncio

from ...get_hash import get_dict_hash
"""
TODO: offload exceptions (as text) to Redis (also allow them to be cleared in Redis?)
TODO: do the same with stdout, stderr
TODO: add some metadata to the above? (when and where it was executed)
"""

from .. import destroyer

TF_KEEP_ALIVE = 20.0 # Keep transformations alive for 20 secs after the last ref has expired

class RemoteTransformer:
    debug = False
    def __init__(self, tf_checksum, peer_id):
        self.tf_checksum = tf_checksum
        self.peer_id = peer_id

def tf_get_buffer(transformation):
    assert isinstance(transformation, dict)
    d = {}
    for k in transformation:
        v = transformation[k]
        if k == "__output__":
            d[k] = v
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
    checksum, celltype, subcelltype, buffer_cache, codename
):
    if celltype not in ("cson", "yaml", "python"):
        return checksum

    buffer = await get_buffer_async(checksum, buffer_cache)    
    if celltype in ("cson", "yaml"):
        semantic_checksum = await convert(
            checksum, buffer, celltype, "plain"
        )
    elif celltype == "python":
        # TODO: consider subcelltype (?)
        value = await deserialize(buffer, checksum, "python", False)
        tree = ast.parse(value, filename=codename)
        dump = ast.dump(tree).encode()
        semantic_checksum = await calculate_checksum(dump)
    else:
        raise TypeError(celltype)
    return semantic_checksum

class TransformationCache:
    _destroyed = False
    def __init__(self):
        self.transformations = {} # tf-checksum-to-transformation
        self.debug = set() # set of debug tf-checksums
        self.transformation_results = {} # tf-checksum-to-(result-checksum, prelim)
        self.transformation_exceptions = {} # tf-checksum-to-exception
        self.transformation_jobs = {} # tf-checksum-to-job
        self.rev_transformation_jobs = {} # job-to-tf-checksum
        self.job_progress = {}

        self.transformer_to_transformations = {} # 1:1, transformations as tf-checksums
        self.transformations_to_transformers = {} # 1:list, transformations as tf-checksums

        self.remote_transformers = {}

        self.syntactic_to_semantic_checksums = {} #checksum-to-checksum
        self.semantic_to_syntactic_checksums = {} #checksum-to-list-of-checksums
        
    @staticmethod
    def syntactic_to_semantic(
        checksum, celltype, subcelltype, buffer_cache, codename
    ):
        future = asyncio.ensure_future(
            syntactic_to_semantic(
                checksum, celltype, subcelltype, buffer_cache, codename
            )
        )
        asyncio.get_event_loop().run_until_complete(future)
        return future.result()

    def register_transformer(self, transformer):
        assert isinstance(transformer, Transformer)
        assert transformer not in self.transformer_to_transformations
        self.transformer_to_transformations[transformer] = None

    @destroyer
    def destroy_transformer(self, transformer):
        assert isinstance(transformer, Transformer)
        tf_checksum = self.transformer_to_transformations.pop(transformer)
        if tf_checksum is not None:
            transformation = self.transformations[tf_checksum]
            self.decref_transformation(transformation, transformer)

    async def update_transformer(self, 
        transformer, celltypes, inputpin_checksums, outputpin, buffer_cache
    ):
        assert isinstance(transformer, Transformer)
        outputname, celltype, subcelltype = outputpin
        transformation = {"__output__": outputpin}
        for pinname, checksum in inputpin_checksums.items():
            pin = transformer._pins[pinname]            
            celltype, subcelltype = celltypes[pinname]
            if checksum is None:
                sem_checksum = None
            else:
                sem_checksum = self.syntactic_to_semantic_checksums.get(checksum)                
                if sem_checksum is None:
                    codename = str(pin)
                    sem_checksum = await syntactic_to_semantic(
                        checksum, celltype, subcelltype, 
                        buffer_cache, codename
                    )
                    if sem_checksum != checksum:
                        self.syntactic_to_semantic_checksums[checksum] = sem_checksum
                        if sem_checksum in self.semantic_to_syntactic_checksums:
                            semsyn = self.semantic_to_syntactic_checksums[sem_checksum]
                        else:
                            semsyn = []
                            self.semantic_to_syntactic_checksums[sem_checksum] = semsyn
                        semsyn.append(checksum)
            transformation[pinname] = celltype, subcelltype, sem_checksum
        await self.incref_transformation(transformation, transformer)

    async def incref_transformation(self, transformation, transformer):
        assert isinstance(transformer, (Transformer, RemoteTransformer))
        if isinstance(transformer, RemoteTransformer):
            key = transformer.tf_checksum, transformer.peer_id
            if key in self.remote_transformers:
                return
            self.remote_transformers[key] = transformer
        from ..manager.tasks.transformer_update import TransformerResultUpdateTask
        tf_buffer = tf_get_buffer(transformation)
        tf_checksum = await calculate_checksum(tf_buffer)
        buffer_cache.incref(tf_checksum) # transformation will be permanently in buffer cache

        if transformer.debug:
            if tf_checksum not in self.debug:
                self.debug.add(tf_checksum)
                self.clear_exception(transformer)
        if tf_checksum not in self.transformations:
            tf = []
            self.transformations_to_transformers[tf_checksum] = tf
            self.transformations[tf_checksum] = transformation
        else:
            tf = self.transformations_to_transformers[tf_checksum]
        if isinstance(transformer, RemoteTransformer):
            old_tf_checksum = None            
        else:
            old_tf_checksum = self.transformer_to_transformations[transformer]
        if old_tf_checksum != tf_checksum:
            if isinstance(transformer, Transformer):
                self.transformer_to_transformations[transformer] = tf_checksum
            tf.append(transformer)
            if old_tf_checksum is not None:
                old_transformation = self.transformations[old_tf_checksum]
                self.decref_transformation(old_transformation, transformer)
        result_checksum, prelim = self._get_transformation_result(tf_checksum)
        if result_checksum is not None and isinstance(transformer, Transformer):
            manager = transformer._get_manager()
            manager._set_transformer_checksum(
                transformer, 
                result_checksum, 
                False,
                prelim=prelim
            )
            TransformerResultUpdateTask(manager, transformer).launch()
        if result_checksum is None or prelim:
            job = self.run_job(transformation)
            if job is not None:                
                await asyncio.shield(job.future)
        
    def decref_transformation(self, transformation, transformer):
        assert isinstance(transformer, (Transformer, RemoteTransformer))
        tf_buffer = tf_get_buffer(transformation)
        tf_checksum = calculate_checksum_sync(tf_buffer)
        assert tf_checksum in self.transformations
        transformers = self.transformations_to_transformers[tf_checksum]
        assert transformer in transformers
        transformers.remove(transformer)
        debug = any([tf.debug for tf in transformers])
        if not debug:
            self.debug.discard(tf_checksum)
        if not len(transformers):
            tempref = functools.partial(self.destroy_transformation, transformation)
            temprefmanager.add_ref(tempref, TF_KEEP_ALIVE)

    def destroy_transformation(self, transformation):
        tf_buffer = tf_get_buffer(transformation)
        tf_checksum = calculate_checksum_sync(tf_buffer)
        assert tf_checksum in self.transformations
        assert tf_checksum in self.transformations_to_transformers
        if len(self.transformations_to_transformers[tf_checksum]):
            return # A new transformer was registered in the meantime
        self.transformations.pop(tf_checksum)
        self.transformations_to_transformers.pop(tf_checksum)
        job = self.transformation_jobs[tf_checksum]
        if job is not None:
            if job.future is not None:
                #print("CANCEL JOB!", job)
                job._cancelled = True
                job.future.cancel()

    def run_job(self, transformation):        
        tf_buffer = tf_get_buffer(transformation)
        tf_checksum = calculate_checksum_sync(tf_buffer)
        transformers = self.transformations_to_transformers[tf_checksum]
        if tf_checksum in self.transformation_exceptions:            
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
        debug = tf_checksum in self.debug
        semantic_cache = {}
        for k,v in transformation.items():
            if k == "__output__":
                continue
            celltype, subcelltype, sem_checksum = v
            if syntactic_is_semantic(celltype, subcelltype):
                continue
            checksums = self.semantic_to_syntactic_checksums[sem_checksum]
            semantic_cache[sem_checksum] = checksums
        job = TransformationJob(
            tf_checksum, codename,
            buffer_cache, transformation, semantic_cache,
            debug
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
            manager = transformer._get_manager()
            manager._set_transformer_progress(
                transformer,
                progress
            )
    
    def prelim_callback(self, job, prelim_checksum):
        if prelim_checksum is None:
            return
        tf_checksum = self.rev_transformation_jobs[id(job)]
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

    def job_done(self, job, _):
        if self._destroyed:
            return
        #print("JOB DONE")

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
        if cancelled:
            return

        transformers = self.transformations_to_transformers[tf_checksum]

        if job._hard_cancelled:
            exc = HardCancelError()
            print("Hard cancel:", job.codename)
        else:
            exc = future.exception()
            if exc is None:
                result_checksum = future.result()
                if result_checksum is None:
                    exc = SeamlessUndefinedError(None)
        if exc is not None:
            try:
                future.result()
            except:
                if not isinstance(exc, HardCancelError):
                    print("!" * 80)
                    if job.remote:
                        print("!      Transformer exception", job.codename)
                    else:
                        print("!      Transformer remote exception", job.codename)
                    print("!" * 80)
                    import traceback
                    traceback.print_exc()
                    print("!" * 80)

        transformation = self.transformations[tf_checksum]
        for transformer in list(transformers):
            if isinstance(transformer, RemoteTransformer):
                self.decref_transformation(transformation, transformer)

        transformers = self.transformations_to_transformers[tf_checksum]

        if exc is not None:
            self.transformation_exceptions[tf_checksum] = exc
            # TODO: offload to provenance? unless hard-canceled
            
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
            return
        self.set_transformation_result(tf_checksum, result_checksum, False)

    def set_transformation_result(self, tf_checksum, result_checksum, prelim):
        from ..manager.tasks.transformer_update import (
            TransformerResultUpdateTask
        )
        self.transformation_results[tf_checksum] = result_checksum, prelim
        if not prelim:
            redis_sinks.set_transformation_result(tf_checksum, result_checksum)
        transformers = self.transformations_to_transformers[tf_checksum]
        for transformer in transformers:
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
            result_checksum = redis_caches.get_transform_result(tf_checksum)
            prelim = False
        return result_checksum, prelim

    async def serve_semantic_to_syntactic(self, sem_checksum, peer_id):
        from ...communion_client import communion_client_manager
        semsyn = self.semantic_to_syntactic_checksums.get(sem_checksum, [])
        if len(semsyn):
            return semsyn
        remote = communion_client_manager.remote_semantic_to_syntactic
        semsyn = await remote(sem_checksum, peer_id)
        return semsyn

    async def serve_get_transformation(self, tf_checksum):
        transformation = self.transformations.get(tf_checksum)
        if transformation is None:
            transformation_buffer = await get_buffer_async(
                tf_checksum, buffer_cache
            )
            if transformation_buffer is not None:
                transformation = json.loads(transformation_buffer)
                for k,v in transformation.items():
                    if k != "__output__":
                        if v[-1] is not None:
                            v[-1] = bytes.fromhex(v[-1])
        return transformation

    async def serve_transformation_status(self, tf_checksum, peer_id):
        from ...communion_client import communion_client_manager
        result_checksum, prelim = self._get_transformation_result(tf_checksum)        
        if result_checksum is not None:
            if not prelim:
                return 3, result_checksum
        running_job = self.transformation_jobs.get(tf_checksum)
        if result_checksum is not None or running_job is not None:
            progress = self.job_progress.get(id(running_job))
            return 2, progress, result_checksum
        if self.transformation_exceptions.get(tf_checksum) is not None:
            return 0, None
        result = await communion_client_manager.remote_transformation_status(
            tf_checksum, peer_id
        )
        if result is not None:
            return result
        transformation = await self.serve_get_transformation(
            tf_checksum
        )
        if transformation is None:
            return -3, None
        remote = communion_client_manager.remote_buffer_status
        for key, value in transformation.items():
            if key == "__output__":
                continue
            celltype, subcelltype, sem_checksum = value
            if syntactic_is_semantic(celltype, subcelltype):                
                sub_checksums = [sem_checksum]
            else:
                sub_checksums = await self.serve_semantic_to_syntactic(
                    sem_checksum, peer_id = None
                )
            for sub_checksum in sub_checksums:
                if buffer_cache.buffer_check(sub_checksum):
                    break
                curr_sub_result = await remote(
                    sub_checksum, peer_id=None
                )
                if curr_sub_result:
                    break
            else:
                return -2, None            
        
        # Seamless instances never return -1 (not runnable), although supervisors may
        return 1, None

    def clear_exception(self, transformer):
        from ..manager.tasks.transformer_update import TransformerUpdateTask
        from ...communion_client import communion_client_manager
        tf_checksum = self.transformer_to_transformations.get(transformer)
        if tf_checksum is None:
            return
        exc = self.transformation_exceptions.pop(tf_checksum, None)
        if exc is None:
            return
        clients = communion_client_manager.clients["transformation"]
        for client in clients:
            coro = client.clear_exception(tf_checksum)
            asyncio.ensure_future(coro)
        for tf in self.transformations_to_transformers[tf_checksum]:
            TransformerUpdateTask(tf._get_manager(), tf).launch()
        

    def hard_cancel(self, transformer):
        tf_checksum = self.transformer_to_transformations.get(transformer)
        if tf_checksum is None:
            return
        job = self.transformation_jobs.get(tf_checksum)
        if job is None:
            return
        self._hard_cancel(job)

    def destroy(self):
        # only called when Seamless shuts down
        a = self.transformer_to_transformations
        if a:
            print("TransformationCache, transformer_to_transformations: %d undestroyed"  % len(a))
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
from ..protocol.get_buffer import get_buffer_async
from ..protocol.conversion import convert
from ..protocol.deserialize import deserialize
from ..protocol.calculate_checksum import calculate_checksum, calculate_checksum_sync
from .redis_client import redis_caches, redis_sinks
from ..transformation import TransformationJob
from ..status import SeamlessInvalidValueError, SeamlessUndefinedError, StatusReasonEnum
from ..transformer import Transformer