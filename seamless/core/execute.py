"""Code for local job execution
Works well under Linux, should work well under OSX"""

import traceback
import multiprocessing
import functools
import time
import sys
import os
import signal
import requests

try:
    import debugpy
except ModuleNotFoundError:
    debugpy = None

from .cached_compile import exec_code, check_function_like
from .protocol.serialize import _serialize as serialize
from ..calculate_checksum import calculate_checksum
from .cache.buffer_cache import buffer_cache
from .cache import buffer_remote
from multiprocessing.pool import ThreadPool, AsyncResult

DIRECT_PRINT = False
NTHREADS_AFTER_FORK = 5

###############################################################################
# Fast unpacking / packing of deep structures
# WARNING: uses threads. Use these functions only *after* forking!
###############################################################################

def fast_unpack(deep_structure, hash_pattern):
    if hash_pattern == {"*": "#"}:
        deep_checksums = list(deep_structure.values())
        celltype = "mixed"
    elif hash_pattern == {"*": "##"}:
        deep_checksums = list(deep_structure.values())
        celltype = None
    elif hash_pattern == {"!": "#"}:
        deep_checksums = deep_structure
        celltype = "mixed"
    else:
        raise NotImplementedError(hash_pattern)
    unpacked_buffers = []
    with ThreadPool(NTHREADS_AFTER_FORK) as pool:
        for n, deep_checksum in enumerate(deep_checksums):
            deep_checksum2 = bytes.fromhex(deep_checksum)
            unpacked_buffer = buffer_cache.buffer_cache.get(deep_checksum2)
            if unpacked_buffer is not None:
                unpacked_buffers.append(unpacked_buffer)
            else:
                unpacked_buffer = pool.apply_async(func=buffer_remote.get_buffer, args = (deep_checksum2,))
                if unpacked_buffer is None:
                    raise CacheMissError(deep_checksum)
                unpacked_buffers.append(unpacked_buffer)
        unpacked_values = []
        for n, (deep_checksum, unpacked_buffer0) in enumerate(zip(deep_checksums, unpacked_buffers)):
            deep_checksum2 = bytes.fromhex(deep_checksum)
            if isinstance(unpacked_buffer0, AsyncResult):
                unpacked_buffer = unpacked_buffer0.get()
                if unpacked_buffer is None:
                    raise CacheMissError(deep_checksum)
            else:
                unpacked_buffer = unpacked_buffer0
            if celltype is None:
                value = unpacked_buffer
            else:
                value = deserialize_sync(unpacked_buffer, deep_checksum2, celltype, copy=False)
                assert value is not None, deep_checksum
            unpacked_values.append(value)

    if hash_pattern == {"!": "#"}:
        return unpacked_values
    else:
        return {k:v for k,v in zip(deep_structure.keys(), unpacked_values)}


def _fast_pack(value, buffer, celltype, database):
    if celltype is None:
        buffer = value
    if buffer is None:        
        buffer = serialize_sync(value, celltype, use_cache=False)        
        if buffer is None:
            return None
    checksum = calculate_checksum_func(buffer)
    if checksum is None:
        # shouldn't ever happen
        return None
    if database.active:
        if celltype is not None:
            buffer_cache.guarantee_buffer_info(checksum, celltype, buffer=buffer, sync_to_remote=True)
        buffer_remote.write_buffer(checksum, buffer)
    return checksum

def fast_pack(unpacked_values, hash_pattern):
    from .protocol.serialize import serialize_cache
    if hash_pattern == {"*": "#"}:
        values = unpacked_values.values()  
        celltype = "mixed"
    elif hash_pattern == {"*": "##"}:
        values = unpacked_values.values()
        celltype = None
    elif hash_pattern == {"!": "#"}:
        values = unpacked_values
        celltype = "mixed"
    else:
        raise NotImplementedError(hash_pattern)
    
    database = database_client.database
    packing_checksums = []
    with ThreadPool(NTHREADS_AFTER_FORK) as pool:
        for n, value in enumerate(values):
            if value is None:
                packing_checksums.append(None)
                continue
            if celltype is None:
                buffer = value
            else:
                buffer, _ = serialize_cache.get((id(value), celltype), (None, None))
            if buffer is not None:
                checksum, _ = calculate_checksum_cache.get(id(buffer), (None, None))
                if checksum is not None:
                    packing_checksums.append(checksum)
                    continue
            packing_checksum = pool.apply_async(func=_fast_pack, args = (value, buffer, celltype, database))
            packing_checksums.append(packing_checksum)
        if hash_pattern in ({"*": "#"}, {"*": "##"}):
            keys = unpacked_values.keys()
            result = {}
        elif hash_pattern == {"!": "*"}:
            keys = range(len(unpacked_values))
            result = [None] * len(unpacked_values)
        else:
            raise AssertionError(hash_pattern)    
        for n, (key, packing_checksum) in enumerate(zip(keys, packing_checksums)):
            if packing_checksum is None:
                result_checksum = None
            elif isinstance(packing_checksum, bytes):
                result_checksum = packing_checksum
            elif isinstance(packing_checksum, AsyncResult):
                result_checksum = packing_checksum.get()
                if result_checksum is None:                
                    raise Exception(key)
            result[key] = result_checksum.hex()
    return result

def unsilk(value):
    if isinstance(value, Silk):
        return unsilk(value.unsilk)
    elif isinstance(value, list):
        return [unsilk(v) for v in value]
    elif isinstance(value, dict):
        result = {}
        for k, v in value.items():
            kk = unsilk(k)
            vv = unsilk(v)
            result[kk] = vv
        return result
    else:
        return value

def return_preliminary(result_queue, celltype, value):
    #print("return_preliminary", value)
    prelim_buffer = serialize(value, celltype)
    if buffer_remote.can_write():
        prelim_checksum = calculate_checksum(prelim_buffer)
        prelim_checksum2 = prelim_checksum.hex()
        buffer_cache.guarantee_buffer_info(prelim_checksum, celltype, sync_to_remote=True)
        buffer_remote.write_buffer(prelim_checksum, prelim_buffer)
        result_queue.put(((2, "checksum"), prelim_checksum2))
    else:
        result_queue.put((2, prelim_buffer))

def set_progress(result_queue, value):
    assert value >= 0 and value <= 100
    result_queue.put((3, value))

def _execute(name, code,
      with_ipython_kernel,
      injector, module_workspace,
      identifier, namespace, deep_structures_to_unpack,
      inputs, output_name, output_celltype, output_hash_pattern,
      result_queue
    ):        
        from .transformation import SeamlessTransformationError, SeamlessStreamTransformationError
        from seamless.highlevel.direct import transformer
        assert identifier is not None
        namespace["return_preliminary"] = functools.partial(
            return_preliminary, result_queue, output_celltype
        )
        namespace["set_progress"] = functools.partial(
            set_progress, result_queue
        )
        namespace["transformer"] = transformer
        try:
            namespace.pop(output_name, None)
            for pinname, value in deep_structures_to_unpack.items():
                deep_structure, hash_pattern = value 
                unpacked_value = fast_unpack(deep_structure, hash_pattern)
                namespace[pinname] = unpacked_value
                namespace["PINS"][pinname] = unpacked_value
            with injector.active_workspace(module_workspace, namespace):
                exec_code(
                    code, identifier, namespace, inputs, output_name, 
                    with_ipython_kernel=with_ipython_kernel
                )
        except SeamlessTransformationError as exc:
            exc = str(exc) + "\n"
            return (2, exc)
        except SeamlessStreamTransformationError as exc:
            exc = str(exc) + "\n"
            return (10, exc)
        except Exception as exc:
            _, _,  tb = sys.exc_info()
            exc_len = len(traceback.extract_tb(tb))
            exc = traceback.format_exc(limit=-(exc_len-2))
            return (1, exc)
        except SystemExit:
            raise SystemExit() from None
        else:
            if output_name is None:
                return (0, None)
            else:
                try:
                    result = namespace[output_name]
                except KeyError:
                    function_like = check_function_like(code, identifier)
                    if function_like:
                        f, d = function_like
                        input_params = ",".join(["{0}={0}".format(inp) for inp in sorted(list(inputs))])
                        msg = """The transformer code contains a single function "{f}" and {d} other statement(s).
Did you mean to:
1. Define the transformer code as a single function "{f}"?
   In that case, you must put the other statements within "def {f}(...):  ".
or
2. Define the transformer code as a code block?
   In that case, you must define the output variable "{output_name}", e.g. add a statement
   "{output_name} = {f}({input_params})" at the end
                        """.format(f=f,d=d, output_name=output_name, input_params=input_params)
                    else:
                        msg = "Output variable name '%s' undefined" % output_name
                    return (1, msg)
                else:
                    try:
                        result = unsilk(result)
                        if database.active:
                            result_queue.put((5, "release lock"))
                        if output_hash_pattern is not None:
                            deep_structure = fast_pack(result, output_hash_pattern)
                            result = deep_structure
                            output_celltype = "mixed"
                        result_buffer = serialize(result, output_celltype)
                        if buffer_remote.can_write():
                            result_checksum = calculate_checksum(result_buffer)
                            result_checksum2 = result_checksum.hex()
                            buffer_cache.guarantee_buffer_info(result_checksum, output_celltype, sync_to_remote=True)
                            buffer_remote.write_buffer(result_checksum, result_buffer)
                            return ((0, "checksum"), result_checksum2)
                        else:
                            return (0, result_buffer)
                    except Exception as exc:
                        exc = traceback.format_exc()
                        return (1, exc)

class FakeStdStreamBuf:
    def __init__(self, parent):
        self._parent = parent
    def write(self, v):
        if not isinstance(v, bytes):
            raise TypeError(type(v))
        parent = self._parent
        parent._buf += v
        if parent._direct_print:
            parent._real.buffer.write(v)

class FakeStdStream:
    def __init__(self, real, direct_print):
        self._buf = b""
        self._real = real
        self._direct_print = direct_print
        self.buffer = FakeStdStreamBuf(self)
    def isatty(self):
        return False
    def write(self, v):        
        self._buf += str(v).encode()
        if self._direct_print:
            self._real.write(v)
    def writelines(self, sequence):
        for s in sequence:
            self.write(s)
    def writeable(self):
        return True
    def flush(self):
        pass
    def read(self):
        try:
            return self._buf.decode()
        except UnicodeDecodeError:
            return self._buf
    def readable(self):
        return True

def execute(name, code,
      with_ipython_kernel,
      injector, module_workspace,
      identifier, namespace,
      deep_structures_to_unpack, inputs,
      output_name, output_celltype, output_hash_pattern,
      result_queue,
      debug = None,
      tf_checksum = None
    ):
    from seamless.util import is_forked
    if is_forked():
        # This is in principle always True
        import seamless
        from .direct.run import TRANSFORMATION_STACK
        if tf_checksum is not None:
            if isinstance(tf_checksum, bytes):
                tf_checksum = tf_checksum.hex()
            TRANSFORMATION_STACK.append(tf_checksum)
        seamless.running_in_jupyter = False
        database_client.session = requests.Session()
        signal.signal(signal.SIGINT, signal.SIG_IGN)

    direct_print = False
    if debug is None:
        debug = {}
    if debug.get("direct_print"):
        direct_print = True
    else:
        direct_print = DIRECT_PRINT
    direct_print_file = debug.get("direct_print_file")
    logs_file = debug.get("logs_file")
    if logs_file is not None:
        try:
            with open(logs_file, "w"):
                pass
        except Exception:
            pass
    if not debug.get("attach", False):
        debug = {}
    if debug != {}:
        from ..metalevel.ide import debug_pre_hook, debug_post_hook
        debug_pre_hook(debug)
    if debug.get("exec-identifier"):
        identifier = debug["exec-identifier"]
    assert identifier is not None

    _exiting = False
    direct_print_filehandle = None
    try:
        old_stdio = sys.stdout, sys.stderr

        ok = False

        if debug.get("python_attach"):
            port = int(debug["python_attach_port"])  # MUST be set right before forking
            print("*" * 80)
            print("Executing transformer %s with Python debugging" % name)
            msg = debug.get("python_attach_message")
            if msg is not None:
                print(msg)
            print("*" * 80) 
            if debugpy is None:
                raise ModuleNotFoundError("No module named 'debugpy'")
            debugpy.listen(("0.0.0.0", port))  # listen for incoming DAP client connections
            debugpy.wait_for_client()  # wait for a client to connect

        if debug.get("generic_attach"):
            print("*" * 80)
            print("Executing transformer %s with generic debugging" % name)
            msg = debug.get("generic_attach_message")
            if msg is not None:
                print(msg)
            else:
                print("Process ID: %s" % os.getpid())
                print("Transformer execution will pause until SIGUSR1 has been received")
            print("*" * 80)
            class DebuggerAttached(Exception):
                pass
            def handler(*args, **kwargs):
                raise DebuggerAttached
            signal.signal(signal.SIGUSR1, handler)
            try:
                time.sleep(3600)
            except DebuggerAttached:
                pass

            direct_print_filehandle = None
            if direct_print:
                if direct_print_file is not None:
                    direct_print_filehandle = open(direct_print_file, "w", buffering=1)
            if direct_print_filehandle is not None:
                stdout = FakeStdStream(direct_print_filehandle, direct_print)
                stderr = FakeStdStream(direct_print_filehandle, direct_print)
            else:
                stdout = FakeStdStream(sys.__stdout__, direct_print)
                stderr = FakeStdStream(sys.__stderr__, direct_print)
            sys.stdout, sys.stderr = stdout, stderr
            start_time = time.time()
            result = _execute(name, code,
                with_ipython_kernel,
                injector, module_workspace,
                identifier, namespace,
                deep_structures_to_unpack,
                inputs, output_name, output_celltype, output_hash_pattern,
                result_queue
            )
        else:
            direct_print_filehandle = None
            if direct_print:
                if direct_print_file is not None:
                    direct_print_filehandle = open(direct_print_file, "w", buffering=1)
            if direct_print_filehandle is not None:
                stdout = FakeStdStream(direct_print_filehandle, direct_print)
                stderr = FakeStdStream(direct_print_filehandle, direct_print)
            else:
                stdout = FakeStdStream(sys.__stdout__, direct_print)
                stderr = FakeStdStream(sys.__stderr__, direct_print)
            sys.stdout, sys.stderr = stdout, stderr
            start_time = time.time()
            result = _execute(name, code,
                with_ipython_kernel,
                injector, module_workspace,
                identifier, namespace,
                deep_structures_to_unpack,
                inputs, output_name, output_celltype, output_hash_pattern,
                result_queue
            )
        execution_time = time.time() - start_time

        msg_code, msg = result
        if msg_code == 2: # SeamlessTransformationError, propagate
            result_queue.put((1, msg))
        elif msg_code in (1, 10):
            std = ""
            sout = stdout.read()
            sys.stdout, sys.stderr = old_stdio
            if len(sout):
                if not len(std):
                    std = "\n"
                std += """*************************************************
* Standard output
*************************************************
{}
*************************************************
""".format(sout)
            serr = stderr.read()
            if len(serr):
                if not len(std):
                    std += "\n"
                std +="""*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(serr)
            if len(std):
                msg = msg + std
            msg +="""*************************************************
Execution time: {:.1f} seconds
""".format(execution_time)
            result_queue.put((1, msg))
        else:
            content = stdout.read()
            if len(content):
                result_queue.put((4, (0, content)))
            content = stderr.read()
            if len(content):
                result_queue.put((4, (1, content)))
            result_queue.put((4, (2, execution_time)))
            result_queue.put(result)
        ok = True
    except SystemExit:
        _exiting = True
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        raise SystemExit() from None
    except Exception:
        sys.stdout, sys.stderr = old_stdio
        traceback.print_exc()
    finally:
        sys.stdout, sys.stderr = old_stdio
        if direct_print_filehandle is not None:
            direct_print_filehandle.close()
        if debug:
            try:
                debug_post_hook(debug)
            except Exception:
                traceback.print_exc()        
        if not _exiting:
            try:
                result_queue.close()
                if ok:
                    result_queue.join()
            except Exception:
                traceback.print_exc()
        kill_children(multiprocessing.current_process())


from silk import Silk
from .cache import database_client, CacheMissError
from .cache.database_client import database
from .protocol.deep_structure import deep_structure_to_value, value_to_deep_structure_sync as value_to_deep_structure
from .protocol.serialize import serialize_sync
from .protocol.deserialize import deserialize_sync
from .protocol.calculate_checksum import calculate_checksum_sync as calculate_checksum, calculate_checksum_func, calculate_checksum_cache
from ..subprocess_ import kill_children