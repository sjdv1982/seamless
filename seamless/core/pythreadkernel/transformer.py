import traceback
from . import Worker
from .killable_thread import KillableThread
from multiprocessing import Process
import functools
import time
import sys
import signal
import platform
from ..cached_compile import cached_compile
from ..injector import transformer_injector

if platform.system() == "Windows":
    from ctypes import windll

USE_PROCESSES = True
if USE_PROCESSES:
    from multiprocessing import JoinableQueue as Queue
    Executor = Process
else:
    from queue import Queue
    Executor = KillableThread

def return_preliminary(result_queue, value):
    #print("return_preliminary", value)
    result_queue.put((-1, value))

def execute(name, code_object, namespace, injector, workspace,
    output_name, result_queue):
    namespace["return_preliminary"] = functools.partial(
        return_preliminary, result_queue
    )
    try:
        namespace.pop(output_name, None)
        with injector.active_workspace(workspace):
            exec(code_object, namespace)
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

def execute_debug(name, code_object, namespace, injector, workspace,
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
    execute(name, code_object, namespace, injector, workspace,
        output_name, result_queue)


class Transformer(Worker):
    name = "transformer"
    injector = transformer_injector
    injected_modules = None
    EXCEPTION = None
    def __init__(self, parent, inputs,
                 output_name, output_queue, output_semaphore,
                 *, in_equilibrium = False, **kwargs):
        self.output_name = output_name
        self.output_queue = output_queue
        self.output_semaphore = output_semaphore

        self.func_name = None
        self.code_object = None
        self.last_result = None
        self.running_thread = None
        self.in_equilibrium = in_equilibrium
        self.debug = False

        o = self.output_name if self.output_name is not None else "_"
        self.function_expr_template = "{0}\n%s = {1}(" % o
        has_inputs = False
        for inp in sorted(list(inputs.keys())):
            if inp == "code":
                continue
            has_inputs = True
            self.function_expr_template += "%s=%s," % (inp, inp)
        if has_inputs:
            self.function_expr_template = self.function_expr_template[:-1]
        self.function_expr_template += ")"

        super(Transformer, self).__init__(parent, inputs, **kwargs)
        injected_modules = []
        for inp in self.inputs:
            pin = self.inputs[inp]
            access_mode = pin[1]
            if access_mode in ("module", "binary_module"):
                injected_modules.append(inp)
        if len(injected_modules):
            self.injected_modules = injected_modules
            self.injector.define_workspace(self, injected_modules)

    def send_message(self, tag, message):
        #print("send_message", tag, message, hex(id(self.output_queue)))
        self.output_queue.append((tag, message))
        self.output_semaphore.release()

    def return_preliminary(self, value):
        #print("return_preliminary", value)
        self.send_message("@PRELIMINARY", (self.output_name, value))

    def update(self, updated, semaphore):
        self.send_message("@START", None)
        ok = False
        try:
            # If code object is updated, recompile
            if "code" in updated:
                identifier = str(self.parent())
                _, access_mode, _ = self.inputs["code"]
                if access_mode == "text":
                    code = self.values["code"]
                    code_obj = None
                else:
                    # Code data object
                    assert access_mode in ("pythoncode", "object")
                    code_obj = self.values["code"]
                    code = code_obj.value
                if code_obj is not None and code_obj.is_function:
                    func_name = code_obj.func_name
                    if func_name == "<expr>":
                        o = self.output_name if self.output_name is not None else "_"
                        expr = "{0} = {1}".format(o, code)
                    elif func_name == "<lambda>":
                        code2 = "LAMBDA = " + code
                        expr = self.function_expr_template.format(code2, "LAMBDA")
                    else:
                        expr = self.function_expr_template.format(code, func_name)
                    self.code_object = cached_compile(expr, identifier, "exec")
                    self.func_name = func_name
                else:
                    self.code_object = cached_compile(code, identifier, "exec")
            # Update namespace of inputs
            keep = {k:v for k,v in self.namespace.items() if k.startswith("_")}
            self.namespace.clear()
            self.namespace.update(keep)
            self.namespace["__fullname__"] = ".".join(self.parent().path)
            self.namespace["__name__"] ="transformer"  #must be the same as injector
            for name in self.inputs:
                if name not in ("code", "schema"):
                    self.namespace[name] = self.values[name]
            queue = Queue()
            workspace = self if self.injected_modules else None
            args = (self.parent()._format_path(), self.code_object,
              self.namespace, self.injector, workspace,
              self.output_name, queue)
            if self.debug and USE_PROCESSES:
                executor = Executor(target=execute_debug,args=args, daemon=True)
                executor.start()
                msg = "%s is running as process %d, waiting for a debugger attachment"
                print(msg % (self.namespace["__fullname__"], executor.pid),
                  file=sys.stderr)
                if platform.system() != "Windows":
                    msg = "After attaching, send the SIGUSR1 signal ('signal SIGUSR1' in GDB)"
                    print(msg, file=sys.stderr)
                msg = "To cancel debugging, set Transformer.debug to False"
                print(msg, file=sys.stderr)
            else:
                executor = Executor(target=execute,args=args, daemon=True)
                executor.start()
                if self.debug:
                    msg = "Seamless is not configured to execute transformers in processes"
                    print(msg, file=sys.stderr)
                    msg = "Debugging of processes will not be possible"
                    print(msg, file=sys.stderr)
            dead_time = 0
            while 1:
                ok = False
                prelim = None
                if executor.is_alive():
                    executor.join(0.01) #10 ms
                else:
                    time.sleep(0.01)
                    dead_time += 0.01
                    if dead_time >= 1:
                        raise Exception #executor died without result or exception
                while not queue.empty():
                    status, msg = queue.get()
                    queue.task_done()
                    if status == -1:
                        prelim = msg
                    elif status == 0:
                        self.EXCEPTION = None
                        result = msg
                        ok = True
                        break
                    elif status == 1:
                        self.EXCEPTION = msg
                        raise Exception(msg)
                if ok:
                    break
                if prelim is not None:
                    self.return_preliminary(prelim)
                    prelim = None
                if semaphore.acquire(blocking=False):
                    semaphore.release()
                    executor.terminate()
                    break
        finally:
            if self.parent() is None:
                ok = False  # parent has died
            else:
                assert self.parent().output_queue is self.output_queue
                self.send_message("@END", None)
                if not ok:
                    time.sleep(2) # For now, give other workers the opportunity to finish
                                  # Won't be necessary anymore when the New Way is there
                    self.send_message("@ERROR", self.EXCEPTION)
        if ok:
            self.last_result = result
            self.send_message(self.output_name, result)
