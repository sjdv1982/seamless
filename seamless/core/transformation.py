"""Schedules asynchronous (transformer) jobs"""
from copy import deepcopy
import weakref
import asyncio
import multiprocessing
from multiprocessing import Process, JoinableQueue as Queue
import sys
import traceback
import functools
import time
import atexit
import json
import orjson
import logging
import importlib
import os
import subprocess
try:
    from prompt_toolkit.patch_stdout import StdoutProxy
except ImportError:
    StdoutProxy = None

logger = logging.getLogger("seamless")

forked_processes = weakref.WeakKeyDictionary()
def _kill_processes():
    for process, termination_time in forked_processes.items():
        if not process.is_alive():
            continue
        kill_time = termination_time + 15  # "docker stop" has 10 secs grace, add 5 secs margin
        ctime = time.time()
        while kill_time > ctime:
            print("Waiting for transformer process to terminate...")
            time.sleep(2)
            if not process.is_alive():
                break
            ctime = time.time()
        if not process.is_alive():
            continue
        print("Killing transformer process... cleanup will not have happened!")
        kill_children(process)
        process.kill()

atexit.register(_kill_processes)

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

class SeamlessTransformationError(Exception):
    pass

class SeamlessStreamTransformationError(Exception):
    pass

###############################################################################
# Local jobs
###############################################################################

_locks = [None] * multiprocessing.cpu_count()

_python_attach_ports = {
    port: None for port in range(5679, 5685)
}

def set_ncores(ncores):
    if ncores == 0:
        print(DeprecationWarning("set_ncores(0) is deprecated. Use seamless.config.block_local() instead"))
    if len(_locks) != ncores:
        if any(_locks):
            msg = "WARNING: Cannot change ncores from %d to %d since there are running jobs"
            print(msg % (len(_locks), ncores), file=sys.stderr)
        else:
            _locks[:] = [None] * ncores

async def acquire_lock(tf_checksum, ncores):
    assert ncores == -1 or ncores > 0
    import random
    if not len(_locks):
        raise SeamlessTransformationError("Local computation has been disabled for this Seamless instance (deprecated)")
    if ncores == -1:
        ncores = len(_locks)
    elif ncores > len(_locks):
        raise SeamlessTransformationError(f"Transformation requires {ncores} cores, but only {len(_locks)} are available")
    while 1:
        result = []
        for locknr, lock in enumerate(_locks):
            if lock is None:
                result.append(locknr)
                if len(result) == ncores:
                    for locknr in result:
                        _locks[locknr] = tf_checksum
                    return result
        
        await asyncio.sleep(0.02 * random.random())

def release_lock(lock):
    for locknr in lock:
        assert _locks[locknr] is not None
        _locks[locknr] = None

async def acquire_python_attach_port(tf_checksum):
    while 1:
        for k in sorted(_python_attach_ports):
            if _python_attach_ports[k] is None:
                _python_attach_ports[k] = tf_checksum
                return k
        await asyncio.sleep(0.01)

def free_python_attach_port(port):
    _python_attach_ports[port] = None

def get_transformation_inputs_output(transformation):
    inputs = []
    as_ = transformation.get("__as__", {})
    for pinname in sorted(transformation.keys()):
        if pinname in ("__compilers__", "__languages__", "__env__", "__as__", "__meta__", "__format__"):
            continue
        if pinname in ("__language__", "__output__"):
            continue
        if pinname == "code":
            continue
        celltype, subcelltype, _ = transformation[pinname]
        if (celltype, subcelltype) == ("plain", "module"):
            pass
        else:
            pinname_as = as_.get(pinname, pinname)
            inputs.append(pinname_as)
    outputpin = transformation["__output__"]
    if len(outputpin) == 3:
        outputname, output_celltype, output_subcelltype = outputpin
        output_hash_pattern = None
    else:
        outputname, output_celltype, output_subcelltype, output_hash_pattern = outputpin
    return inputs, outputname, output_celltype, output_subcelltype, output_hash_pattern

async def build_transformation_namespace(transformation, semantic_cache, codename):        
    namespace = {
        "__name__": "transformer",
        "__package__": "transformer",
    }
    code = None
    deep_structures_to_unpack = {}
    inputs = []
    namespace["PINS"] = {}
    output_hash_pattern = transformation["__output__"][3] if len(transformation["__output__"]) == 4 else None
    namespace["OUTPUTPIN"] = transformation["__output__"][1], output_hash_pattern
    modules_to_build = {}
    as_ = transformation.get("__as__", {})
    FILESYSTEM = {}
    for pinname in sorted(transformation.keys()):
        if pinname in ("__compilers__", "__languages__", "__env__", "__as__", "__meta__", "__format__"):
            continue
        if pinname in ("__language__", "__output__"):
            continue
        celltype, subcelltype, sem_checksum0 = transformation[pinname]
        sem_checksum = bytes.fromhex(sem_checksum0) if sem_checksum0 is not None else None
        if syntactic_is_semantic(celltype, subcelltype):
            checksum = sem_checksum
        else:
            # For now, assume that the first syntactic checksum gives a value
            semkey = sem_checksum, celltype, subcelltype
            checksum = semantic_cache[semkey][0]
        if checksum is None:
            continue
        from_filesystem = False
        hash_pattern = None
        fmt = transformation.get("__format__", {}).get(pinname)
        if fmt is not None:
            fs = fmt.get("filesystem")
            fs_result = None
            if fs is not None:
                optional = fs["optional"]
                mode = fs["mode"]
                if mode == "file":
                    fs_result = None # TODO
                    ### fs_result = buffer_remote.get_filename(checksum)
                else: # mode == "directory"
                    fs_result = None # TODO
                    ### fs_result = buffer_remote.get_directory(checksum)
                fs_entry = deepcopy(fs)
                if fs_result is None:
                    if not optional:
                        msg = "{}: could not find file/directory for {}"
                        raise CacheMissError(msg.format(pinname, checksum.hex()))
                    fs_entry["filesystem"] = False
                else:
                    fs_entry["filesystem"] = True
                    value = fs_result
                    from_filesystem = True
                FILESYSTEM[pinname] = fs_entry

            if fs_result is None:
                hash_pattern = fmt.get("hash_pattern")

        if not from_filesystem:
            # fingertipping must have happened before, but database could be there
            buffer = get_buffer(checksum, remote=True)
            if buffer is None:
                raise CacheMissError(checksum.hex())
            try:
                if hash_pattern is not None:
                    deep_value = await deserialize(buffer, checksum, "plain", False)
                    pinname_as = as_.get(pinname, pinname)
                    inputs.append(pinname_as)
                    deep_structures_to_unpack[pinname_as] = deep_value, hash_pattern
                    continue
                else:
                    value = await deserialize(buffer, checksum, celltype, False)
            except Exception:
                e = traceback.format_exc()
                raise Exception(pinname, e) from None
            if value is None:
                raise CacheMissError(pinname, codename, buffer)
        if pinname == "code":
            code = value
        elif (celltype, subcelltype) == ("plain", "module"):
            modules_to_build[pinname] = value
        else:
            pinname_as = as_.get(pinname, pinname)
            namespace["PINS"][pinname_as] = value
            namespace[pinname_as] = value
            inputs.append(pinname_as)
    for pinname in transformation:
        if pinname in (
            "__language__", "__output__", "__env__", "__compilers__",
            "__languages__", "__as__", "__meta__", "__format__"
        ):
            continue
        celltype, _, _ = transformation[pinname]
        if celltype != "silk":
            continue
        schema_pinname = pinname + "_SCHEMA"
        schema_pin = transformation.get(schema_pinname)
        schema = None
        if schema_pin is not None:
            schema_celltype, _, _ = schema_pin
            assert schema_celltype == "plain", (schema_pinname, schema_celltype)
            schema = namespace[schema_pinname]
        pinname_as = as_.get(pinname, pinname)
        if schema is None and isinstance(namespace[pinname_as], Scalar):
            continue
        if schema is None:
            schema = {}
        v = Silk(
            data=namespace[pinname_as],
            schema=schema
        )
        namespace["PINS"][pinname_as] = v
        namespace[pinname_as] = v
    namespace["FILESYSTEM"] = FILESYSTEM
    return code, namespace, modules_to_build, deep_structures_to_unpack

###############################################################################
# Remote jobs
###############################################################################

REMOTE_TIMEOUT = 5.0

class RemoteJobError(SeamlessTransformationError):
    pass

###############################################################################

class TransformationJob:
    _job_id_counter = 0
    _cancelled = False
    _hard_cancelled = False
    remote_futures = None
    remote_status = None
    remote_clients = None
    remote_result = None
    start = None
    execution_metadata = None
    def __init__(self,
        checksum, codename,
        transformation,
        semantic_cache, *, debug, fingertip,
        scratch=False,
        cannot_be_local=False
    ):        
        self.checksum = checksum
        assert codename is not None
        self.codename = codename
        assert transformation.get("__language__") in ("python", "bash"), transformation.get("__language__")
        assert "code" in transformation, transformation.keys()
        for pinname in transformation:
            if pinname in ("__compilers__", "__languages__", "__as__", "__meta__", "__format__"):
                continue
            if pinname != "__output__":
                assert transformation[pinname][2] is not None, pinname
        self.job_id = TransformationJob._job_id_counter + 1
        TransformationJob._job_id_counter += 1
        self.transformation = transformation
        self.semantic_cache = semantic_cache
        self.debug = debug
        self.fingertip = fingertip
        self.executor = None
        self.future = None
        self.remote = False
        self.restart = False
        self.n_restarted = 0
        self.scratch = scratch
        self.cannot_be_local = cannot_be_local

    async def _probe_remote(self, clients, meta):
        # TODO: see TODO document
        if not len(clients):
            return
        coros = []
        for client in clients:
            coro = client.status(self.checksum, meta)
            coros.append(coro)
        futures = [asyncio.ensure_future(coro) for coro in coros]
        rev = {fut:n for n,fut in enumerate(futures)}

        best_client = None
        best_status = None
        self.remote_result = None
        while 1:
            done, pending = await asyncio.wait(
                futures,
                timeout=REMOTE_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED
            )
            for fut in done:
                if fut.exception() is not None:
                    try:
                        fut.result()
                    except Exception:
                        exc = traceback.format_exc()
                        print_debug("Transformation {}: {}".format(self.checksum.hex(), exc))
                    continue
                try:
                    result = "<unknown>"
                    result = fut.result()
                    status = result[0]
                    if status == 2:
                        status, _, _ = result
                    else:
                        status, response = result
                        if status == 0:
                            exception = response
                except Exception:
                    print_debug("STATUS RESULT", result)
                    print_debug(traceback.format_exc())
                    continue
                if not isinstance(status, int):
                    continue
                if status < 0:
                    continue
                if best_status is None or status > best_status:
                    best_status = status
                    best_client = rev[fut]
                if status == 3:
                    self.remote = True
                    self.remote_status = 3
                    self.remote_clients = None
                    self.remote_result = response
                    for fut in pending:
                        fut.cancel()
                    return
            if not len(pending) or not len(done):
                #print("BEST STATUS", best_status)
                if best_status is None:
                    return
                self.remote = True
                if best_status == 0:
                    self.remote_status = 0
                    self.remote_result = exception
                    return
                if best_status == 1:
                    client = clients[best_client]
                    self.remote_status = best_status
                    self.remote_clients = [client]
                    return
                best_clients = []
                for n, fut in enumerate(futures):
                    if fut.exception() is not None:
                        continue
                    try:
                        status = fut.result()[0]
                    except Exception:
                        continue
                    if status == best_status:
                        best_clients.append(clients[n])
                assert len(best_clients)
                self.remote_status = best_status
                self.remote_clients = best_clients
                break
        #print("PROBE DONE", self.remote_status)


    def execute(self, prelim_callback, progress_callback):
        coro = self._execute(prelim_callback, progress_callback)
        self.future = asyncio.ensure_future(coro)
        self.future.add_done_callback(
            functools.partial(
                transformation_cache.job_done,
                self
            )
        )

    async def _execute(self, prelim_callback, progress_callback):
        while not transformation_cache.active:
            await asyncio.sleep(0.05)
        meta = self.transformation.get("__meta__")
        meta = deepcopy(meta)
        from seamless.config import get_delegate_level
        if get_delegate_level() == 4:
            self.remote = True # previous: call self._probe_remote ...
        if self.remote:
            try:
                result = await self._execute_remote(
                    prelim_callback, progress_callback
                )
                logs = None
            finally:
                self.remote_futures = None
        else:
            result, logs = await self._execute_local(
                prelim_callback, progress_callback
            )
        if self.restart:
            self.n_restarted += 1
            if self.n_restarted > 100:
                raise SeamlessTransformationError("Restarted transformation 100 times")
            self.restart = False
            result, logs = await self._execute(
                prelim_callback, progress_callback
            )
        return result, logs

    async def _execute_remote(self,
        prelim_callback, progress_callback
    ):
        from seamless.assistant_client import run_job
        tf_dunder = {}
        tf = self.transformation
        for k in ("__compilers__", "__languages__", "__meta__", "__env__"):
            if k in tf:
                tf_dunder[k] = tf[k]
        if tf_dunder.get("__meta__", {}).get("local", OverflowError) != OverflowError:
            meta = tf_dunder["__meta__"].copy()
            meta.pop("local")
            tf_dunder["__meta__"] = meta
        try:
            result = await run_job(self.checksum, tf_dunder)
        except RuntimeError as exc:
            raise RemoteJobError(str(exc)) from None
        if result is None:
            self.remote = False
            return
        return bytes.fromhex(result)
        '''
        # TODO, see TODO document. Probably rip this. 
        meta = self.transformation.get("__meta__")
        meta = deepcopy(meta)
        if meta is not None and meta.get("local") == False:
            remote_only = True
        else:
            remote_only = False
        async def get_result1(client):
            try:
                await client.submit(self.checksum, meta)
                result = await client.status(self.checksum, meta)
                return result
            except asyncio.CancelledError:
                if self._hard_cancelled:
                    await client.hard_cancel(self.checksum)
                raise

        async def get_result2(client):
            try:
                await client.wait(self.checksum)
                return await client.status(self.checksum, meta)
            except asyncio.CancelledError:
                if self._hard_cancelled:
                    await client.hard_cancel(self.checksum)
                elif self._cancelled:
                    await client.cancel(self.checksum)
                raise

        if self.remote_status == 3:
            result_checksum = self.remote_result
            return result_checksum
        if self.remote_status == 0:
            exc_str = self.remote_result
            raise RemoteJobError(exc_str)
        elif self.remote_status == 1:
            get_result = get_result1
        elif self.remote_status == 2:
            get_result = get_result2
        else:
            raise ValueError(self.remote_status)
        clients = self.remote_clients
        assert len(clients)

        futures = []
        self.remote_futures = futures
        rev = {}
        for n, client in enumerate(clients):
            future = asyncio.ensure_future(get_result(client))
            futures.append(future)
            rev[future] = n

        has_exceptions = False
        has_negative_status = False
        while 1:
            done, pending = await asyncio.wait(
                futures,
                timeout=REMOTE_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED
            )
            go_on = (len(pending) > 0)
            status = None
            for future in done:
                if future.exception() is not None:
                    try:
                        future.result()
                    except Exception:
                        exc = traceback.format_exc()
                        print_debug("Transformation {}: {}".format(self.checksum.hex(), exc))
                    continue
                try:
                    result = future.result()
                    status = result[0]
                except Exception:
                    exc = traceback.format_exc()
                    print_debug("Transformation {}: {}".format(self.checksum.hex(), exc))
                    continue
                if not isinstance(status, int):
                    continue
                if status == 0:
                    has_exceptions = True
                    exc_str = result[1]
                elif status < 0:
                    has_negative_status = True
                elif status not in (2, 3): # erroneous behaviour
                    continue
                elif status == 2:
                    _, progress, prelim_checksum = result
                    progress_callback(self, progress)
                    prelim_callback(self, prelim_checksum)
                    n = rev.pop(future)
                    futures.remove(future)
                    client = clients[n]
                    get_result = get_result2
                    new_future = asyncio.ensure_future(get_result(client))
                    rev[new_future] = n
                    futures.append(new_future)
                    go_on = True
                    continue
                else: # status == 3
                    _, response = result
                    return response
            if not go_on:
                break
        if status == 1 and get_result is get_result1:
            self.restart = True
            return
        elif has_negative_status and not has_exceptions and not remote_only:
            self.restart = True
            self.remote = False
        elif has_exceptions:
            raise RemoteJobError(exc_str)
        else:
            raise RemoteJobError()
        '''


    async def _execute_local(self,
        prelim_callback, progress_callback
    ):
        from .direct import set_parent_process_queue, set_parent_process_response_queue
        from seamless.util import is_forked
        from seamless.metalevel.unbashify import unbashify
        if self.cannot_be_local:
            raise SeamlessTransformationError("Local computation has been disabled for this Seamless instance")
        with_ipython_kernel = False

        get_global_info()
        self.execution_metadata = deepcopy(execution_metadata0)
        if "Executor" not in self.execution_metadata:
            self.execution_metadata["Executor"] = "seamless-internal"

        transformation = self.transformation
        if transformation.get("__language__") == "bash":
            transformation = unbashify(transformation, self.semantic_cache, self.execution_metadata)
 
        meta = transformation.get("__meta__", {})
        meta = deepcopy(meta)
        if meta.get("local") == False:
            raise RuntimeError("Local execution has been disabled for this transformation")
        job_ncores = meta.get("ncores", 1)

        env_checksum0 = transformation.get("__env__")
        if env_checksum0 is not None:
            env_checksum = bytes.fromhex(env_checksum0)
            env = get_buffer(env_checksum, remote=True)
            if env is None:
                raise CacheMissError(env_checksum.hex())
            env = json.loads(env.decode())
            assert env is not None
            validate_environment(env)
            if "powers" in env and "ipython" in env["powers"]:
                with_ipython_kernel = True

        logs = [None, None, None]
        lock = await acquire_lock(self.checksum, job_ncores)    

        io = get_transformation_inputs_output(transformation)
        inputs, outputname, output_celltype, output_subcelltype, output_hash_pattern = io
        tf_namespace = await build_transformation_namespace(
            transformation, self.semantic_cache, self.codename
        )
        code, namespace, modules_to_build, deep_structures_to_unpack = tf_namespace

        debug = None
        if self.debug is not None:
            debug = deepcopy(self.debug)

        module_workspace = {}
        compilers = transformation.get("__compilers__", default_compilers)
        languages = transformation.get("__languages__", default_languages)
        module_debug_mounts = None
        if debug is not None:
            module_debug_mounts = debug.get("module_mounts")

        full_module_names = build_all_modules(
            modules_to_build, module_workspace,
            compilers=compilers, languages=languages,
            module_debug_mounts=module_debug_mounts
        )
        assert code is not None

        async def get_result_checksum(result_buffer):
            if result_buffer is None:
                return None
            try:
                result_checksum = await calculate_checksum(result_buffer)
                # execute.py will have done a successful serialization for output_celltype
                buffer_cache.guarantee_buffer_info(
                    result_checksum, output_celltype,
                    sync_to_remote=True
                )
                output_celltype2 = "plain" if output_hash_pattern is not None else output_celltype
                validate_evaluation_subcelltype(
                    result_checksum, result_buffer,
                    output_celltype2, output_subcelltype,
                    self.codename
                )
            except Exception:
                raise SeamlessInvalidValueError(result) from None
            return result_checksum

        self.start = time.time()
        running = False
        try:
            run_transformation_futures = []
            python_attach_port = None

            if multiprocessing.get_start_method(allow_none=True) is None:
                multiprocessing.set_start_method("fork")
            assert multiprocessing.get_start_method(allow_none=False) == "fork"

            queue = Queue()
            rqueue = Queue()

            args = (
                self.codename, code,
                with_ipython_kernel,
                injector, module_workspace,
                self.codename,
                namespace, deep_structures_to_unpack,
                inputs, outputname, output_celltype, output_hash_pattern,
                self.scratch,
                queue,
            )
            if debug is not None:
                if debug.get("python_attach"):
                    python_attach_port = await acquire_python_attach_port(self.checksum)
                    debug["python_attach_port"] = python_attach_port
                if full_module_names:
                    debug["full_module_names"] = full_module_names
            kwargs = {}
            kwargs["tf_checksum"] = self.checksum
            if debug is not None:
                kwargs["debug"] = debug

            stdout_orig = sys.stdout
            stderr_orig = sys.stderr
            try:
                if StdoutProxy is not None:
                    if isinstance(stdout_orig, StdoutProxy):
                        sys.stdout = sys.__stdout__
                    if isinstance(stderr_orig, StdoutProxy):
                        sys.stderr = sys.__stderr__
                # Set daemon = False so that transformers can spawn their own transformations.
                # daemon was True in Seamless 0.10 and before!
                # Multiprocessing processes aren't true Unix daemons,
                # and "daemon" is a multiprocessing-only thing.
                # Looking at the source, daemon = False should have no impact,
                #  but we must make sure to kill all transformer children

                #if is_forked():
                #    from .direct.run import _parent_process_queue, _parent_process_response_queue
                #    assert _parent_process_queue is not None
                #    assert _parent_process_response_queue is not None

                assert not is_forked()
                set_parent_process_queue(queue)
                set_parent_process_response_queue(rqueue)

                print_info(f"Local execution of transformation job: {self.checksum.hex()}, forked = {is_forked()}")
                self.executor = Process(target=execute,args=args, kwargs=kwargs, daemon=False)
                self.executor.start()
            finally:
                sys.stdout = stdout_orig
                sys.stderr = stderr_orig
            running = True
            result = None
            done = False
            result_checksum = None
            while 1:
                while not queue.empty():
                    status, msg = queue.get()
                    queue.task_done()
                    if isinstance(status, int):
                        if status == 0:
                            result_buffer = msg
                            done = True
                            break
                        elif status == 1:
                            raise SeamlessTransformationError(msg)
                        elif status == 2:
                            prelim_buffer = msg
                            prelim_checksum = await get_result_checksum(prelim_buffer)
                            buffer_cache.cache_buffer(prelim_checksum, prelim_buffer)
                            prelim_callback(self, prelim_checksum)
                        elif status == 3:
                            progress = msg
                            progress_callback(self, progress)
                        elif status == 4:
                            # 1: stdout, 2: stderr, 3: execution time
                            code, content = msg
                            try:
                                if code in (0, 1):
                                    content = str(content)
                            except Exception:
                                pass
                            else:
                                if isinstance(content, (bytes, str)) and len(content) > 10000:
                                    skipped = len(content)-5000-4960
                                    content2 = content[:4960]
                                    content2 += "\n...(skipped %d characters)...\n" % skipped
                                    content2 += content[-5000:]
                                    content = content2
                                logs[code] = content
                        elif status == 5:
                            if msg == "release lock":
                                if lock is not None:
                                    release_lock(lock)
                                lock = None
                            else:
                                raise Exception("Unknown return message '{}'".format(msg))
                        elif status == 6:
                            if msg == "acquire lock":
                                assert lock is None
                                lock = await acquire_lock(self.checksum, job_ncores)
                            else:
                                raise Exception("Unknown return message '{}'".format(msg))
                        elif status == 7:
                            # run_transformation
                            tf_checksum, tf_dunder, syntactic_cache, fingertip = msg
                            assert not is_forked()
                            for celltype, subcelltype, buf in syntactic_cache:
                                # TODO: create a transformation_cache method and invoke it, common with other code
                                syn_checksum = await calculate_checksum(buf)
                                buffer_cache.incref_buffer(syn_checksum, buf, persistent=False)
                                sem_checksum = await syntactic_to_semantic(
                                    syn_checksum, celltype, subcelltype, 
                                    self.codename + ":@transformer"
                                )
                                key = (syn_checksum, celltype, subcelltype)
                                transformation_cache.syntactic_to_semantic_checksums[key] = sem_checksum
                                semkey = (sem_checksum, celltype, subcelltype)
                                s2s = transformation_cache.semantic_to_syntactic_checksums
                                if semkey not in s2s:
                                    s2s[semkey] = []
                                s2s[semkey].append(syn_checksum)
                                database.set_sem2syn(semkey, s2s[semkey])
                                buffer_cache.cache_buffer(syn_checksum, buf)
                                buffer_cache.decref(syn_checksum)
                            print_info(f"Nested local transformation job`: {tf_checksum}, forked = {is_forked()}")
                            fut = asyncio.ensure_future(
                                run_transformation_async(tf_checksum, tf_dunder=tf_dunder, fingertip=fingertip)
                            )
                            def fut_done(fut):
                                print_info(f"Finished nested local transformation job: {tf_checksum}")
                                try:
                                    checksum = fut.result()
                                    logs = transformation_cache.transformation_logs.get(bytes.fromhex(tf_checksum))
                                except Exception:
                                    checksum = None
                                    logs = None
                                rqueue.put((tf_checksum, checksum, logs))
                                print_info(f"FINISHED nested local transformation job: {tf_checksum}")
                            fut.add_done_callback(fut_done)
                            run_transformation_futures.append(fut)
                        else:
                            raise Exception("Unknown return status {}".format(status))
                    elif isinstance(status, tuple) and len(status) == 2 and status[1] == "checksum":
                        status = status[0]
                        if status == 0:
                            result_checksum = bytes.fromhex(msg)
                            done = True
                            break
                        elif status == 2:
                            prelim_checksum = bytes.fromhex(msg)
                            prelim_callback(self, prelim_checksum)
                        else:
                            raise Exception("Unknown return status ({}, 'checksum')".format(status))
                    else:
                        raise Exception("Unknown return status {}".format(status))
                if not self.executor.is_alive():
                    if self.executor.exitcode != 0:
                        raise SeamlessTransformationError(
                          "Transformation exited with code %s\n" % self.executor.exitcode
                        )
                    if not done:
                        raise SeamlessTransformationError("Transformation exited without result")
                if done:
                    break
                fut_done = []
                for fut in run_transformation_futures:
                    if fut.done():
                        try:
                            cs = fut.result()
                        except Exception as exc:
                            msg = traceback.format_exc()
                            if running:
                                self.executor.terminate()
                                forked_processes[self.executor] = time.time()
                            raise SeamlessTransformationError(msg) from None
                        else:
                            fut_done.append(fut)
                for fut in fut_done:
                    run_transformation_futures.remove(fut)
                await asyncio.sleep(0.01)
            if not self.executor.is_alive():
                self.executor = None
        except asyncio.CancelledError:
            if running:
                self.executor.terminate()
                forked_processes[self.executor] = time.time()
            raise asyncio.CancelledError from None
        finally:
            if python_attach_port is not None:
                free_python_attach_port(python_attach_port)
            for fut in run_transformation_futures:
                try:
                    fut.cancel()
                except Exception:
                    pass
            if lock is not None:
                release_lock(lock)
        print_info(f"Finished local execution of transformation job: {self.checksum.hex()}")
        if result_checksum is None:
            assert result_buffer is not None
            result_checksum = await get_result_checksum(result_buffer)
            assert result_checksum is not None
        if result_buffer is not None:
            buffer_cache.cache_buffer(result_checksum, result_buffer)
            try:
                result_str = result_buffer.decode()
                try:
                    result_str = str(orjson.loads(result_str))
                except Exception:
                    pass
                if len(result_str) > 10000:
                    skipped = len(result_str)-5000-4960
                    result_str2 = result_str[:4960]
                    result_str2 += "\n...(skipped %d characters)...\n" % skipped
                    result_str2 += result_str[-5000:]
                    result_str = result_str2

            except UnicodeDecodeError:
                result_str = "<binary buffer of length {}, checksum {}>".format(
                    len(result_buffer), result_checksum.hex()
                )
        else:
            result_str = "<checksum {}>".format(result_checksum.hex())
        logstr = """*************************************************
* Result
*************************************************
{}
""".format(result_str)
        if logs[0] is not None:
            logstr += """*************************************************
* Standard output
*************************************************
{}
""".format(logs[0])
        if logs[1] is not None:
            logstr += """*************************************************
* Standard error
*************************************************
{}
""".format(logs[1])

        if logs[2] is not None:
            execution_time = logs[2]
            try:
                execution_time = "{:.1f}".format(execution_time)
            except Exception:
                execution_time = str(execution_time)
            logstr += """*************************************************
Execution time: {} seconds
""".format(execution_time)

        logstr += "*************************************************"
        self.execution_metadata["Execution time (seconds)"] = execution_time
        return result_checksum, logstr


from silk import Silk, Scalar
from .execute import execute
from .injector import transformer_injector as injector
from .build_module import build_all_modules
from ..compiler import compilers as default_compilers, languages as default_languages
from .protocol.get_buffer import get_buffer
from .protocol.deserialize import deserialize
from .protocol.calculate_checksum import calculate_checksum, calculate_checksum_func
from .protocol.evaluate import validate_evaluation_subcelltype
from .cache import CacheMissError
from .cache.buffer_cache import buffer_cache
from .cache.transformation_cache import transformation_cache, syntactic_is_semantic, syntactic_to_semantic
from .status import SeamlessInvalidValueError
from .environment import validate_environment
from ..subprocess_ import kill_children
from .. import run_transformation_async

execution_metadata0 = {}

if os.environ.get("DOCKER_IMAGE"):
    execution_metadata0["Docker image"] = os.environ["DOCKER_IMAGE"]
    if os.environ.get("DOCKER_VERSION"):
        execution_metadata0["Docker version"] = os.environ["DOCKER_VERSION"]

_got_global_info = False
def get_global_info(global_info=None):
    global _got_global_info
    if _got_global_info:
        return execution_metadata0.copy()
    if not database.active:
        return {}
    if global_info is not None:
        execution_metadata0.update(global_info)
        _got_global_info = True
        return execution_metadata0.copy()

    seamless_version = "development"
    try:
        import conda.cli.python_api
        conda.cli.python_api.run_command
        conda.cli.python_api.Commands.LIST
    except (ImportError, AttributeError):
        pass
    else:
        info = subprocess.getoutput("conda env export")
        info = "\n".join([l for l in info.splitlines() if not l.startswith("name:")])
        conda_env_checksum = calculate_checksum_func(info, hex=True)
        execution_metadata0["Conda environment checksum"] = conda_env_checksum
        buffer_remote.write_buffer(conda_env_checksum, info)
        buffer_cache.cache_buffer(bytes.fromhex(conda_env_checksum), info.encode())
        info = conda.cli.python_api.run_command(conda.cli.python_api.Commands.LIST, ["-f", "seamless-framework"])[0]
        for l in info.split("\n"):
            l = l.strip()
            if l.startswith("#"):
                continue
            ll = l.split()
            if len(ll) < 2:
                continue
            if ll[0] != "seamless-framework":
                continue
            seamless_version = ll[1]
    if seamless_version == "development":
        try:
            seamless_version = importlib.metadata.version("seamless-framework")
        except importlib.metadata.PackageNotFoundError:
            pass
    execution_metadata0["Seamless version"] = seamless_version

    commands = {
        "Memory": "lshw -C memory -short | tail -n +3",
        "CPU": "lshw -C cpu -short | tail -n +3",
        "GPU": 'nvidia-smi --query-gpu "name,memory.total" --format=csv,noheader',
        "GPU2": "lshw -C display -short | tail -n +3",
    }
    result = {}
    for field, cmd in commands.items():
        if field == "GPU2":
            if "GPU" in result:
                continue
            field = "GPU"
        proc = subprocess.run(cmd, shell=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode or not proc.stdout:
            continue
        result[field] = proc.stdout.decode()
    execution_metadata0.update(result)
    _got_global_info = True
    return execution_metadata0.copy()

from .cache import buffer_remote
from .cache.database_client import database
