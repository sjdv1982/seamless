##TODO: refactor for in-thread (for Qt)

import weakref
from . import Process
from ...dtypes.objects import PythonBlockObject
from ...dtypes import data_type_to_data_object

class Editor(Process):
    name = "editor"

    class EditorOutput:
        def __init__(self, parent, name):
            self._parent = weakref.ref(parent)
            self._name = name
        def set(self, value):
            p = self._parent()
            if p is None:
                return
            p.output_queue.append((self._name, value))
            p.output_semaphore.release()

    def __init__(self, namespace, input_data_types, output_names, output_queue, output_semaphore, lock, **kwargs):
        assert "code_start" not in input_data_types
        assert "code_stop" not in input_data_types
        assert "code_update" not in input_data_types

        self.namespace = namespace
        self.input_data_types = input_data_types
        self.output_names = output_names
        self.output_queue = output_queue
        self.output_semaphore = output_semaphore
        self.lock = lock

        inputs = {name: data_type_to_data_object(value)(name, value) for name, value in input_data_types.items()}
        inputs["code_start"] = PythonBlockObject("code_start", ("text", "code", "python"))
        inputs["code_stop"] = PythonBlockObject("code_stop", ("text", "code", "python"))
        inputs["code_update"] = PythonBlockObject("code_update", ("text", "code", "python"))
        self._set_namespace()

        super(Editor, self).__init__(inputs, **kwargs)

    def _set_namespace(self):
        self.namespace.clear()
        self.namespace["_cache"] = {}
        for o in self.output_names:
            self.namespace[o] = self.EditorOutput(self, o)

    def update(self, updated):
        with self.lock:
            do_update = False
            if "code_update" in updated:
                code = self.values["code_update"].data
                self.code_update_block = compile(
                    code, self.name + "_update", "exec"
                )
                do_update = True

            # Update namespace of inputs
            for name in self.inputs.keys():
                if name in updated:
                    self.namespace[name] = self.values[name].data
                    do_update = True
            if do_update:
                exec(self.code_update_block, self.namespace)
