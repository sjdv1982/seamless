import traceback
from . import Worker
###from ...dtypes.objects import PythonTransformerCodeObject
###from ...dtypes import data_type_to_data_object
from .killable_thread import KillableThread
from multiprocessing import Process
import functools
import time

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

def execute(name, code_object, namespace, output_name, result_queue):
    namespace["return_preliminary"] = functools.partial(
        return_preliminary, result_queue
    )
    try:
        namespace.pop(output_name, None)
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

    def __init__(self, parent, inputs, output_name, output_queue, output_semaphore, **kwargs):
        self.output_name = output_name
        self.output_queue = output_queue
        self.output_semaphore = output_semaphore

        self.func_name = None
        self.code_object = None
        self.last_result = None
        self.running_thread = None

        self.function_expr_template = "%%s\n%s  = {0}(" % self.output_name
        for inp in sorted(list(inputs)):
            self.function_expr_template += "%s=%s," % (inp, inp)
        self.function_expr_template = self.function_expr_template[:-1] + ")"

        all_inputs = list(inputs) + ["code"]
        super(Transformer, self).__init__(parent, all_inputs, **kwargs)


    def return_preliminary(self, value):
        #print("return_preliminary", value)
        self.output_queue.append(("@PRELIMINARY", (self.output_name, value)))
        self.output_semaphore.release()

    def update(self, updated, semaphore):
        self.output_queue.append(("@START", None))
        self.output_semaphore.release()
        ok = False
        try:
            # Code data object
            code_obj = self.values["code"]

            # If code object is updated, recompile
            if "code" in updated:
                code = code_obj.value
                func_name = code_obj.func_name
                if code_obj.is_function:
                    expr = self.function_expr_template.format(code, func_name)
                    self.code_object = compile(expr, self.name, "exec")
                    self.func_name = func_name
                else:
                    self.code_object = compile(code, self.name, "exec")
            # Update namespace of inputs
            keep = {k:v for k,v in self.namespace.items() if k.startswith("_")}
            self.namespace.clear()
            self.namespace.update(keep)
            self.namespace["__name__"] = self.name
            for name in self.inputs:
                self.namespace[name] = self.values[name]
            queue = Queue()
            args = (self.parent().format_path(), self.code_object, self.namespace, self.output_name, queue)
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
            self.output_queue.append(("@END", None))
            self.output_semaphore.release()
        if ok:
            self.last_result = result
            self.output_queue.append((self.output_name, result))
            self.output_semaphore.release()
