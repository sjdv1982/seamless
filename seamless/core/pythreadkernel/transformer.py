import traceback
from . import Worker
from ...dtypes.objects import PythonTransformerCodeObject
from ...dtypes import data_type_to_data_object
from .killable_thread import KillableThread
from multiprocessing import Process
import functools
import time
from ...silk.classes import SilkObject

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

def execute(name, expression, namespace, result_queue):
    namespace["return_preliminary"] = functools.partial(
        return_preliminary, result_queue
    )
    try:
        result = eval(expression, namespace)
    except:
        exc = traceback.format_exc()
        result_queue.put((1, exc))
    else:
        if isinstance(result, SilkObject):
            result = result.json()
        result_queue.put((0, result))
    if USE_PROCESSES:
        result_queue.close()
    result_queue.join()

class Transformer(Worker):
    name = "transformer"

    def __init__(self, parent, input_data_types, output_name, output_queue, output_semaphore, **kwargs):
        assert "code" not in input_data_types

        self.input_data_types = input_data_types
        self.output_name = output_name
        self.output_queue = output_queue
        self.output_semaphore = output_semaphore

        self.func_name = None
        self.expression = None
        self.last_result = None
        self.running_thread = None

        inputs = {name: data_type_to_data_object(value)(name, value) for name, value in input_data_types.items()}
        inputs["code"] = PythonTransformerCodeObject("code", ("text", "code", "python"))

        super(Transformer, self).__init__(parent, inputs, **kwargs)

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
            func = code_obj.code
            func_name = code_obj.func_name

            # If code object is updated, recompile
            if "code" in updated:
                expr = "{0}()".format(func_name)
                self.expression = compile(expr, self.name, "eval")
                self.func_name = func_name
                exec(func, self.namespace)

            # Update namespace of inputs
            for name in self.inputs.keys():
                if name in updated:
                    self.namespace[name] = self.values[name].data
            queue = Queue()
            args = (self.parent().format_path(), self.expression, self.namespace, queue)
            executor = Executor(target=execute,args=args, daemon=True) #TODO: name
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
