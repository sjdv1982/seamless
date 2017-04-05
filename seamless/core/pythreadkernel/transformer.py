from . import Worker
from ...dtypes.objects import PythonTransformerCodeObject
from ...dtypes import data_type_to_data_object

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

        inputs = {name: data_type_to_data_object(value)(name, value) for name, value in input_data_types.items()}
        inputs["code"] = PythonTransformerCodeObject("code", ("text", "code", "python"))

        super(Transformer, self).__init__(parent, inputs, **kwargs)

    def update(self, updated):
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

        # Place result in output
        result = eval(self.expression, self.namespace)
        self.last_result = result
        self.output_queue.append((self.output_name, result))
        self.output_semaphore.release()
