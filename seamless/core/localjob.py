import traceback
import multiprocessing
from multiprocessing import Process
import functools
import time
import sys
import os
import signal
import platform

from .killable_thread import KillableThread
from .cached_compile import cached_compile
###from .injector import transformer_injector

### TODO: injectors are not yet working


if platform.system() == "Windows":
    from ctypes import windll

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

def execute(name, code, identifier, namespace,
    output_name, result_queue):
    namespace["return_preliminary"] = functools.partial(
        return_preliminary, result_queue
    )
    try:
        code_object = cached_compile(code, identifier, "exec")
        ###if USE_PROCESSES and multiprocessing.get_start_method() != "fork":
        ###    injector.restore()
        namespace.pop(output_name, None)
        ###with injector.active_workspace(workspace):
        ###    exec(code_object, namespace)
        exec(code_object, namespace) ###
    except:
        exc = traceback.format_exc()
        print(exc)
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

def execute_debug(name, code, identifier, namespace,
    output_name, result_queue):
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
    execute(name, code, identifier, namespace,
        output_name, result_queue)

