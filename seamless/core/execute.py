"""Code for local job execution
Works well under Linux, should work well under OSX"""

import traceback
import multiprocessing
from multiprocessing import Process
import functools
import time
import sys
import os
import signal
import platform
import threading
import inspect
import ctypes
import wurlitzer

# TODO: decide when to kill an execution job!

from .cached_compile import exec_code
from .protocol.serialize import _serialize as serialize

DIRECT_PRINT = False

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

def _async_raise(tid, exctype):
    """raises the exception, performs cleanup if needed"""
    if not inspect.isclass(exctype):
        exctype = type(exctype)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        # """if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect"""
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

class KillableThread(threading.Thread):
    def kill(self, exctype=SystemError):
        if not self.isAlive():
            return
        tid = self.ident
        _async_raise(tid, exctype)
    terminate = kill

USE_PROCESSES = os.environ.get("SEAMLESS_USE_PROCESSES")
if USE_PROCESSES is None:
    USE_PROCESSES = True
    if multiprocessing.get_start_method() != "fork":
        USE_PROCESSES = False
else:
    if USE_PROCESSES == "0" or USE_PROCESSES.upper() == "FALSE":
        USE_PROCESSES = False
if USE_PROCESSES:
    from multiprocessing import JoinableQueue as Queue
    Executor = Process
else:
    from queue import Queue
    Executor = KillableThread

def return_preliminary(result_queue, celltype, value):
    #print("return_preliminary", value)
    prelim_buffer = serialize(value, celltype)
    result_queue.put((2, prelim_buffer))

def set_progress(result_queue, value):
    assert value >= 0 and value <= 100
    result_queue.put((3, value))

def _execute(name, code,
      injector, module_workspace,
      identifier, namespace,
      inputs, output_name, celltype, result_queue
    ):
        from .transformation import SeamlessTransformationError, SeamlessStreamTransformationError
        assert identifier is not None
        namespace["return_preliminary"] = functools.partial(
            return_preliminary, result_queue, celltype
        )
        namespace["set_progress"] = functools.partial(
            set_progress, result_queue
        )
        try:
            namespace.pop(output_name, None)
            if len(module_workspace):
                with injector.active_workspace(module_workspace, namespace):
                    exec_code(code, identifier, namespace, inputs, output_name)
            else:
                exec_code(code, identifier, namespace, inputs, output_name)
        except SeamlessTransformationError as exc:
            exc = str(exc) + "\n"
            return (2, exc)
        except SeamlessStreamTransformationError as exc:
            exc = str(exc) + "\n"
            return (10, exc)
        except Exception as exc:
            exc = traceback.format_exc()
            return (1, exc)
        except SystemExit:
            raise SystemExit() from None
        else:
            if output_name is None:
                return (0, None)
            else:
                try:
                    result = namespace[output_name]
                    result = unsilk(result)
                    result_buffer = serialize(result, celltype)
                    return (0, result_buffer)
                except KeyError:
                    return (1, "Output variable name '%s' undefined" % output_name)

class FakeStdStream:
    def __init__(self, real):
        self._buf = ""
        self._real = real
    def isatty(self):
        return False
    def write(self, v):
        self._buf += str(v)
    def writelines(self, sequence):
        for s in sequence:
            self.write(s)
    def writeable(self):
        return True
    def flush(self):
        pass
    def read(self):
        return self._buf
    def readable(self):
        return True

def execute(name, code,
      injector, module_workspace,
      identifier, namespace,
      inputs, output_name, celltype, result_queue,
      python_debug = None
    ):
    if python_debug:
        direct_print = True
    else:
        direct_print = DIRECT_PRINT
    assert identifier is not None
    _exiting = False
    try:
        ok = False
        if direct_print:
            result = _execute(name, code,
                injector, module_workspace,
                identifier, namespace,
                inputs, output_name, celltype, result_queue
            )
        else:
            old_stdio = sys.stdout, sys.stderr
            stdout, stderr = FakeStdStream(sys.stdout), FakeStdStream(sys.stderr)
            sys.stdout, sys.stderr = stdout, stderr
            with wurlitzer.pipes() as (stdout2, stderr2):
                result = _execute(name, code,
                    injector, module_workspace,
                    identifier, namespace,
                    inputs, output_name, celltype, result_queue
                )

        msg_code, msg = result
        if msg_code == 2: # SeamlessTransformationError, propagate
            result_queue.put((1, msg))
        elif msg_code in (1, 10):
            std = ""
            if not direct_print:
                sout = stdout.read() + stdout2.read()
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
                serr = stderr.read() + stderr2.read()
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
                msg = std + msg
            result_queue.put((1, msg))
        else:
            if not direct_print:
                """ # does not normally work...
                sys.stdout.write(stdout.read() + stdout2.read())
                sys.stderr.write(stderr.read() + stderr2.read())
                """
                content = stdout.read() + stdout2.read()
                if len(content):
                    result_queue.put((4, (0, content)))
                content = stderr.read() + stderr2.read()
                if len(content):
                    result_queue.put((4, (1, content)))
            result_queue.put(result)
        ok = True
    except SystemExit:
        _exiting = True
        if USE_PROCESSES:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
        raise SystemExit() from None
    except Exception:
        traceback.print_exc()
    finally:
        if not direct_print:
            sys.stdout, sys.stderr = old_stdio
        if not _exiting:
            try:
                if USE_PROCESSES:
                    result_queue.close()
                if ok:
                    result_queue.join()
            except Exception:
                traceback.print_exc()


def execute_debug(name, code,
      injector, module_workspace,
      identifier, namespace,
      inputs, output_name, celltype, result_queue,
      **args
    ):
    _exiting = False
    direct_print = DIRECT_PRINT
    try:
        ok = False
        old_stdio = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__

        print("*" * 80)
        print("Executing transformer %s in debug mode" % name)
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
        result = _execute(name, code,
            injector, module_workspace,
            identifier, namespace,
            inputs, output_name, celltype, result_queue
        )
        result_queue.put(result)
        ok = True
    except SystemExit:
        _exiting = True
        if USE_PROCESSES:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
        raise SystemExit() from None
    except Exception:
        traceback.print_exc()
    finally:
        if not direct_print:
            sys.stdout, sys.stderr = old_stdio
        if not _exiting:
            try:
                if USE_PROCESSES:
                    result_queue.close()
                if ok:
                    result_queue.join()
            except Exception:
                traceback.print_exc()

from ..silk import Silk