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
import loky
loky.backend.context.set_start_method("fork") ###
from loky.process_executor import TerminatedWorkerError

_queues = {}

def execute2(*args, **kwargs):
    print("CHILD", _queues)
    queue = _queues[args[-1]]
    args2 = args[:-1] + (queue,)
    execute(*args2, **kwargs)

try:
    from prompt_toolkit.patch_stdout import StdoutProxy
except ImportError:
    StdoutProxy = None

logger = logging.getLogger("seamless")

running_executors = weakref.WeakKeyDictionary()
def _kill_processes():
    for future, termination_time in running_executors.items():
        if future.done():
            continue
        executor = future.EXECUTOR()
        if executor is None:
            continue
        kill_time = termination_time + 15  # "docker stop" has 10 secs grace, add 5 secs margin
        ctime = time.time()
        while kill_time > ctime:
            print("Waiting for transformer process to terminate...")
            time.sleep(2)
            if future.done():
                break
            ctime = time.time()
        if future.done():
            continue
        print("Killing transformer process... cleanup will not have happened!")
        #kill_children(process)
        #process.kill()
        future.cancel()
        executor.shutdown(wait=False)

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
    if len(_locks) != ncores:
        if any(_locks):
            msg = "WARNING: Cannot change ncores from %d to %d since there are running jobs"
            print(msg % (len(_locks), ncores), file=sys.stderr)
        else:
            _locks[:] = [None] * ncores

async def acquire_lock(tf_checksum):
    if not len(_locks):
        raise SeamlessTransformationError("Local computation has been disabled for this Seamless instance")
    while 1:
        for locknr, lock in enumerate(_locks):
            if lock is None:
                _locks[locknr] = tf_checksum
                return locknr
        await asyncio.sleep(0.01)

def release_lock(locknr):
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
    from .cache.database_client import database_cache
    namespace = {
        "__name__": "transformer",
        "__package__": "transformer",
    }
    code = None
    deep_structures_to_unpack = {}
    inputs = []
    namespace["PINS"] = {}
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
                    fs_result = database_cache.get_filename(checksum)
                else: # mode == "directory"
                    fs_result = database_cache.get_directory(checksum)
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
    def __init__(self,
        checksum, codename,
        transformation,
        semantic_cache, *, debug,
    ):
        self.checksum = checksum
        assert codename is not None
        self.codename = codename
        assert transformation.get("__language__") == "python", transformation.get("__language__")
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
        self.execute_future = None
        self.future = None
        self.remote = False
        self.restart = False
        self.n_restarted = 0

    async def _probe_remote(self, clients, meta):
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
        clients = list(communion_client_manager.clients["transformation"])
        if self.debug is None:
            await self._probe_remote(clients, meta)
        if self.remote:
            self.remote_futures = None
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


    async def _execute_local(self,
        prelim_callback, progress_callback
    ):
        from .. import database_sink
        with_ipython_kernel = False

        meta = self.transformation.get("__meta__")
        meta = deepcopy(meta)
        if meta is not None and meta.get("local") == False:
            raise RuntimeError("Local execution has been disabled for this transformation")

        env_checksum0 = self.transformation.get("__env__")
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
        lock = await acquire_lock(self.checksum)

        io = get_transformation_inputs_output(self.transformation)
        inputs, outputname, output_celltype, output_subcelltype, output_hash_pattern = io
        tf_namespace = await build_transformation_namespace(
            self.transformation, self.semantic_cache, self.codename
        )
        code, namespace, modules_to_build, deep_structures_to_unpack = tf_namespace

        debug = None
        if self.debug is not None:
            debug = deepcopy(self.debug)

        module_workspace = {}
        compilers = self.transformation.get("__compilers__", default_compilers)
        languages = self.transformation.get("__languages__", default_languages)
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
        hqueue = None
        try:
            run_transformation_futures = []
            python_attach_port = None

            if multiprocessing.get_start_method(allow_none=True) is None:
                multiprocessing.set_start_method("fork")
            assert multiprocessing.get_start_method(allow_none=False) == "fork"            

            queue = Queue()
            rqueue = Queue()

            hqueue = id(queue)
            _queues[hqueue] = queue
            args = (
                self.codename, code,
                with_ipython_kernel,
                injector, module_workspace,
                self.codename,
                namespace, deep_structures_to_unpack,
                inputs, outputname, output_celltype, output_hash_pattern,
                ###queue,
                hqueue
            )
            print("MAIN", _queues)
            if debug is not None:
                if debug.get("python_attach"):
                    python_attach_port = await acquire_python_attach_port(self.checksum)
                    debug["python_attach_port"] = python_attach_port
                if full_module_names:
                    debug["full_module_names"] = full_module_names
            kwargs = {}
            if debug is not None:
                kwargs["debug"] = debug

            stdout_orig = sys.stdout
            stderr_orig = sys.stderr
            try:
                executor = loky.get_reusable_executor()
                if StdoutProxy is not None:
                    if isinstance(stdout_orig, StdoutProxy):
                        sys.stdout = sys.__stdout__
                    if isinstance(stderr_orig, StdoutProxy):
                        sys.stderr = sys.__stderr__
                imperative._set_parent_process_queue(queue)
                imperative._set_parent_process_response_queue(rqueue)
                '''
                func = functools.partial(execute, *args, **kwargs)
                self.execute_future = asyncio.get_event_loop().run_in_executor(
                    executor, func
                )
                '''
                self.execute_future = executor.submit(execute2, *args, **kwargs)
                #self.execute_future = executor.submit(execute, *args, **kwargs)
                self.execute_future.EXECUTOR = executor

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
                                release_lock(lock)
                                lock = None
                            else:
                                raise Exception("Unknown return message '{}'".format(msg))
                        elif status == 6:
                            if msg == "acquire lock":
                                assert lock is None
                                lock = await acquire_lock(self.checksum)
                            else:
                                raise Exception("Unknown return message '{}'".format(msg))
                        elif status == 7:
                            # run_transformation
                            tf_checksum, metalike, syntactic_cache = msg
                            for celltype, subcelltype, buf in syntactic_cache:
                                # TODO: create a transformation_cache method and invoke it, common with other code
                                syn_checksum = await calculate_checksum(buf)
                                buffer_cache.incref_buffer(syn_checksum, buf, False)
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
                                database_sink.sem2syn(semkey, s2s[semkey])
                                buffer_cache.cache_buffer(syn_checksum, buf)
                                buffer_cache.decref(syn_checksum)
                            fut = asyncio.ensure_future(
                                run_transformation_async(tf_checksum, metalike)
                            )
                            def fut_done(fut):
                                try:
                                    checksum = fut.result()
                                    logs = transformation_cache.transformation_logs.get(bytes.fromhex(tf_checksum))                                    
                                except Exception:
                                    checksum = None
                                    logs = None
                                rqueue.put((checksum, logs))
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
                if self.execute_future.done():
                    '''
                    if self.execute_future.exitcode != 0:
                        raise SeamlessTransformationError(
                          "Transformation exited with code %s\n" % self.execute_future.exitcode
                        )
                    '''
                    exc = self.execute_future.exception()
                    if exc is not None:
                        # uncaught exception
                        raise SeamlessTransformationError(str(exc)) ### TODO
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
                                self.execute_future.terminate()
                                running_executors[self.execute_future] = time.time()
                            raise SeamlessTransformationError(msg) from None
                        else:
                            fut_done.append(fut)
                for fut in fut_done:
                    run_transformation_futures.remove(fut)
                await asyncio.sleep(0.01)
            if not self.execute_future.is_alive():
                self.execute_future = None
        except asyncio.CancelledError:
            if running:
                self.execute_future.terminate()
                running_executors[self.execute_future] = time.time()
            raise asyncio.CancelledError from None
        finally:
            ###if hqueue is not None:
            ###    _queues.pop(hqueue, None)
            if python_attach_port is not None:
                free_python_attach_port(python_attach_port)
            for fut in run_transformation_futures:
                try:
                    fut.cancel()
                except Exception:
                    pass
            if lock is not None:
                release_lock(lock)
        if result_checksum is None:
            assert result_buffer is not None
            result_checksum = await get_result_checksum(result_buffer)
            assert result_checksum is not None
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
        return result_checksum, logstr


from silk import Silk, Scalar
from .execute import execute
from .injector import transformer_injector as injector
from .build_module import build_all_modules
from ..compiler import compilers as default_compilers, languages as default_languages
from .protocol.get_buffer import get_buffer
from .protocol.deserialize import deserialize
from .protocol.calculate_checksum import calculate_checksum
from .protocol.evaluate import validate_evaluation_subcelltype
from .cache import CacheMissError
from .cache.buffer_cache import buffer_cache
from .cache.transformation_cache import transformation_cache, syntactic_is_semantic, syntactic_to_semantic
from .status import SeamlessInvalidValueError
from ..communion_client import communion_client_manager
from .environment import validate_environment
from ..subprocess_ import kill_children
from .. import imperative
from .. import run_transformation_async