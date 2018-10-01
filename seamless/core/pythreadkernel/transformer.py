import traceback
from . import Worker
from .killable_thread import KillableThread
from multiprocessing import Process
import functools
import time
from ..cached_compile import cached_compile
from ..injector import transformer_injector

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
        result_queue.put((1, exc))
    else:
        try:
            result = namespace[output_name]
            result_queue.put((0, result))
        except KeyError:
            result_queue.put((1, "Output variable name '%s' undefined" % output_name))
    if USE_PROCESSES:
        result_queue.close()
    result_queue.join()

class Transformer(Worker):
    name = "transformer"
    injector = transformer_injector
    injected_modules = None
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

        self.function_expr_template = "{0}\n%s = {1}(" % self.output_name
        for inp in sorted(list(inputs.keys())):
            if inp == "code":
                continue
            self.function_expr_template += "%s=%s," % (inp, inp)
        self.function_expr_template = self.function_expr_template[:-1] + ")"

        super(Transformer, self).__init__(parent, inputs, **kwargs)
        injected_modules = []
        for inp in self.inputs:
            pin = self.inputs[inp]
            access_mode = pin[1]
            if access_mode == "module":
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
                        expr = "{0} = {1}".format(self.output_name, code)
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
            self.namespace["__name__"] = self.name
            for name in self.inputs:
                if name not in ("code", "schema"):
                    self.namespace[name] = self.values[name]
            queue = Queue()
            workspace = self if self.injected_modules else None
            args = (self.parent()._format_path(), self.code_object,
              self.namespace, self.injector, workspace,
              self.output_name, queue)
            executor = Executor(target=execute,args=args, daemon=True)
            executor.start()
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
                        result = msg
                        ok = True
                        break
                    elif status == 1:
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
            assert self.parent().output_queue is self.output_queue
            self.send_message("@END", None)
        if ok:
            self.last_result = result
            self.send_message(self.output_name, result)
