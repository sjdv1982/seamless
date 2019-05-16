"""Code for local job execution
Works well under Linux, should work well under OSX
Contains some support code for Windows, but completely untested"""

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
if platform.system() == "Windows":
    from ctypes import windll


from .cached_compile import exec_code
###from .injector import transformer_injector

### TODO: injectors are not yet working

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

def return_preliminary(result_queue, value):
    #print("return_preliminary", value)
    result_queue.put((-1, value))

def execute(name, code, 
      injector, module_workspace,
      identifier, namespace,
      inputs, output_name, result_queue
    ):
    namespace["return_preliminary"] = functools.partial(
        return_preliminary, result_queue
    )
    try:
        namespace.pop(output_name, None)
        if len(module_workspace):
            with injector.active_workspace(module_workspace, namespace):
                exec_code(code, identifier, namespace, inputs, output_name)
        else:
            exec_code(code, identifier, namespace, inputs, output_name)
    except:
        exc = traceback.format_exc()
        result_queue.put((1, exc))
    else:
        if output_name is None:
            result_queue.put((0, None))
        else:
            try:
                result = namespace[output_name]
                result_queue.put((0, result))
            except KeyError:
                result_queue.put((1, "Output variable name '%s' undefined" % output_name))
    if USE_PROCESSES:
        result_queue.close()
    result_queue.join()

def execute_debug(name, code, 
      injector, module_workspace,
      identifier, namespace,
      inputs, output_name, result_queue
    ):
    if platform.system() == "Windows":
        while True:
            if windll.kernel32.IsDebuggerPresent() != 0:
                break
            time.sleep(0.1)
    else:
        class DebuggerAttached(Exception):
            pass
        def handler(*args, **kwargs):
            raise DebuggerAttached
        signal.signal(signal.SIGUSR1, handler)
        try:
            time.sleep(3600)
        except DebuggerAttached:
            pass
    execute(name, code, 
      injector, module_workspace,
      identifier, namespace,
      inputs, output_name, result_queue
    )

