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
from numpy import multiply
import wurlitzer
import debugpy

from .cached_compile import exec_code, check_function_like
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

from multiprocessing import JoinableQueue as Queue


def return_preliminary(result_queue, celltype, value):
    #print("return_preliminary", value)
    prelim_buffer = serialize(value, celltype)
    result_queue.put((2, prelim_buffer))

def set_progress(result_queue, value):
    assert value >= 0 and value <= 100
    result_queue.put((3, value))

def _execute(name, code,
      with_ipython_kernel,
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
                    exec_code(
                        code, identifier, namespace, inputs, output_name, 
                        with_ipython_kernel=with_ipython_kernel
                    )
            else:
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
                except KeyError:
                    function_like = check_function_like(code, identifier)
                    if function_like:
                        f, d = function_like
                        input_params = ",".join(["{0}={0}".format(inp) for inp in sorted(list(inputs))])
                        msg = """The transformer code contains a single function "{f}" and {d} other statement(s).
Did you mean to:
1. Define the transformer code as a pure function "{f}"?
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
                        result_buffer = serialize(result, celltype)
                        return (0, result_buffer)
                    except Exception as exc:
                        exc = traceback.format_exc()
                        return (1, exc)

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
      with_ipython_kernel,
      injector, module_workspace,
      identifier, namespace,
      inputs, output_name, celltype, result_queue,
      debug = None,
    ):
    if multiprocessing.current_process().name != "MainProcess":
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    direct_print = False    
    if debug is None:
        debug = {}
    elif not debug.get("attach", False):
        debug = {}
    if debug != {}:
        from ..metalevel.ide import debug_pre_hook, debug_post_hook
        debug_pre_hook(debug)
    if debug.get("direct_print"):
        direct_print = True
    else:
        direct_print = DIRECT_PRINT
    if debug.get("exec-identifier"):
        identifier = debug["exec-identifier"]
    assert identifier is not None

    _exiting = False
    try:
        old_stdio = sys.stdout, sys.stderr

        ok = False        

        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__

        if debug.get("python_attach"):
            port = int(debug["python_attach_port"])  # MUST be set right before forking
            print("*" * 80)
            print("Executing transformer %s with Python debugging" % name)
            msg = debug.get("python_attach_message")
            if msg is not None:
                print(msg)
            print("*" * 80)        
            debugpy.listen(("localhost", port))  # listen for incoming DAP client connections
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

        if direct_print:
            result = _execute(name, code,
                with_ipython_kernel,
                injector, module_workspace,
                identifier, namespace,
                inputs, output_name, celltype, result_queue
            )
        else:
            stdout, stderr = FakeStdStream(sys.stdout), FakeStdStream(sys.stderr)
            sys.stdout, sys.stderr = stdout, stderr
            with wurlitzer.pipes() as (stdout2, stderr2):
                result = _execute(name, code,
                    with_ipython_kernel,
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
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        raise SystemExit() from None
    except Exception:
        sys.stdout, sys.stderr = old_stdio
        traceback.print_exc()
    finally:
        if debug:
            try:
                debug_post_hook(debug)
            except Exception:
                traceback.print_exc()
        if not direct_print:
            sys.stdout, sys.stderr = old_stdio
        if not _exiting:
            try:
                result_queue.close()
                if ok:
                    result_queue.join()
            except Exception:
                traceback.print_exc()


from silk import Silk