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

    def __init__(self,
        namespace, input_data_types,
        output_names, output_queue, output_semaphore,
        gui_queue,
        **kwargs
    ):
        assert "code_start" not in input_data_types
        assert "code_stop" not in input_data_types
        assert "code_update" not in input_data_types

        self.namespace = namespace
        self.namespace.clear()
        self.namespace["_cache"] = {}
        self.input_data_types = input_data_types
        self.output_names = output_names
        self.output_queue = output_queue
        self.output_semaphore = output_semaphore
        self._active = False

        inputs = {name: data_type_to_data_object(value)(name, value) for name, value in input_data_types.items()}
        inputs["code_start"] = PythonBlockObject("code_start", ("text", "code", "python"))
        inputs["code_update"] = PythonBlockObject("code_update", ("text", "code", "python"))
        inputs["code_stop"] = PythonBlockObject("code_stop", ("text", "code", "python"))
        self._set_namespace()

        super(Editor, self).__init__(inputs, **kwargs)

    def _set_namespace(self):
        self.namespace.clear()
        self.namespace["_cache"] = {}
        for o in self.output_names:
            self.namespace[o] = self.EditorOutput(self, o)

    def _cleanup(self):
        self._code_stop()

    def _code_stop(self):
        if self._active:
            exec(self.code_stop_block, self.namespace)
            self._active = False
            self._set_namespace()

    def _code_start(self):
        assert not self._active
        exec(self.code_start_block, self.namespace)
        self._active = True

    def update(self, updated):

        do_update = False

        # If any code object is updated, recompile
        if "code_stop" in updated:
            code = self.values["code_stop"].data
            self.code_stop_block = compile(code, self.name + "_stop", "exec")

        if "code_start" in updated:
            self._code_stop()
            code = self.values["code_start"].data
            self.code_start_block = compile(code, self.name + "_start", "exec")
            self._code_start()
            do_update = True

        if "code_update" in updated:
            code = self.values["code_update"].data
            self.code_update_block = compile(
                code, self.name + "_update", "exec"
            )
            do_update = True

        # Update namespace of inputs
        assert self._active
        for name in self.inputs.keys():
            if name in updated:
                self.namespace[name] = self.values[name].data
                do_update = True
        if do_update:
            exec(self.code_update_block, self.namespace)
