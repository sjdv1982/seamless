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
        except Exception:
            exc = traceback.format_exc()
            return (1, exc)
        else:
            if output_name is None:
                return (0, None)
            else:
                try:
                    result = namespace[output_name]
                    result_buffer = serialize(result, celltype)
                    return (0, result_buffer)
                except KeyError:
                    return (1, "Output variable name '%s' undefined" % output_name)

def execute(name, code, 
      injector, module_workspace,
      identifier, namespace,
      inputs, output_name, celltype, result_queue
    ):
    assert identifier is not None
    try:
        old_stdio = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
        with wurlitzer.pipes() as (stdout, stderr):
            result = _execute(name, code, 
                injector, module_workspace,
                identifier, namespace,
                inputs, output_name, celltype, result_queue
            )
        code, msg = result
        if code == 1:
            std = ""
            sout = stdout.read()
            if len(sout):
                if not len(std):
                    std = "\n"
                std += "*" * 50 + "\n"
                std += "* STDOUT:" + " " * 40 + "*\n"
                std += "*" * 50 + "\n"
                std += sout
                std += "*" * 50 + "\n"
                std += "\n"
            serr = stderr.read()
            if len(serr):
                if not len(std):
                    std += "\n"
                std += "*" * 50 + "\n"
                std += "* STDERR:" + " " * 40 + "*\n"
                std += "*" * 50 + "\n"
                std += serr
                std += "*" * 50 + "\n"
                std += "\n"
            if len(std):
                msg = std + msg
            result_queue.put((code, msg))
        else:
            print(stdout.read())
            print(stderr.read(), file=sys.stderr)
            result_queue.put(result)
    finally:
        sys.stdout, sys.stderr = old_stdio
        if USE_PROCESSES:
            result_queue.close()
        result_queue.join()

def execute_debug(name, code, 
      injector, module_workspace,
      identifier, namespace,
      inputs, output_name, celltype, result_queue
    ):    
    try:
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
    finally:
        sys.stdout, sys.stderr = old_stdio
        if USE_PROCESSES:
            result_queue.close()
        result_queue.join()

