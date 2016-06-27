from . import Process
from ..datatypes.objects import DataObject, PythonTransformerObject
from datatypes import datatype_to_dataobject

class Transformer(Process):
    name = "transformer"
    def __init__(self, input_datatypes, output_queue, output_semaphore):
        assert "code"  not in input_datatypes
        self.namespace = {}
        self.input_datatypes = input_datatypes        
        self.output_queue = output_queue
        self.output_semaphore = output_semaphore
        inputs = {}
        for name, value in input_datatypes.items():
            inputs[name] = datatype_to_dataobject(value)(name,value)
        inputs["code"] = PythonTransformerObject("code", ("text", "code", "python"))
        Process.__init__(self, inputs)
    def update(self, updated):
        func, func_name = self.value["code"].code, self.value["code"].func_name
        if "code" in updated:
            expr = "{0}(input)".format(func_name)
            self.expression = compile(expr, self.name, "eval")
            self.func_name = func_name
            exec(func, self.namespace)
        for inputname in self.inputs.keys():
            if inputname in updated:
                self.namespace[inputname] = self.value[inputname].data
        result = eval(self.expression, self.namespace)
        self.output_queue.append(result)
        self.output_semaphore.release()
