
import weakref
from ...dtypes.objects import PythonBlockObject
from ...dtypes import data_type_to_data_object

class Editor:
    name = "editor"

    class EditorOutput:
        def __init__(self, parent, name):
            self._parent = weakref.ref(parent)
            self._name = name
        def set(self, value):
            p = self._parent()
            if p is None:
                return
            p.parent().output_update(self._name, value)

    def __init__(self,
        parent,
        input_data_types,output_names
    ):
        assert "code_start" not in input_data_types
        assert "code_stop" not in input_data_types
        assert "code_update" not in input_data_types

        self.parent = weakref.ref(parent)
        self.namespace = {}
        self.input_data_types = input_data_types
        self.output_names = output_names


        inputs = {name: data_type_to_data_object(value)(name, value) for name, value in input_data_types.items()}
        inputs["code_start"] = PythonBlockObject("code_start", ("text", "code", "python"))
        inputs["code_stop"] = PythonBlockObject("code_stop", ("text", "code", "python"))
        inputs["code_update"] = PythonBlockObject("code_update", ("text", "code", "python"))
        self.inputs = inputs
        self._pending_inputs = {name for name in inputs.keys()}
        self.values = {name: None for name in inputs.keys()}
        self.exception = None
        self.updated = set()
        self._active = False
        self._set_namespace()

    def process_input(self, name, data):        
        data_object = self.inputs[name]
        # instance of datatypes.objects.DataObject

        try:
            data_object.parse(data)
            data_object.validate()

        except Exception as exc:
            self.exception = exc
            import traceback
            traceback.print_exc()
            return

        # If we have missing values, and this input is currently default, it's no longer missing
        if self._pending_inputs and self.values[name] is None:
            self._pending_inputs.remove(name)

        self.values[name] = data_object
        self.updated.add(name)

        # With all inputs now present, we can issue updates
        if not self._pending_inputs:
            self.update(self.updated)
            self.updated = set()

    def _code_stop(self):
        if self._active:
            exec(self.code_stop_block, self.namespace)
            self._active = False
            self.editor._set_namespace()

    def _code_start(self):
        assert not self._active
        exec(self.code_start_block, self.namespace)
        self._active = True


    def _set_namespace(self):
        self.namespace.clear()
        self.namespace["_cache"] = {}
        for o in self.output_names:
            self.namespace[o] = self.EditorOutput(self, o)


    def update(self, updated):
        # If any code object is updated, recompile
        if "code_stop" in updated:
            code = self.values["code_stop"].data
            self.code_stop_block = compile(code, self.name + "_stop", "exec")

        if "code_start" in updated:
            code = self.values["code_start"].data
            self._code_stop()
            self.code_start_block = compile(code, self.name + "_start", "exec")
            self._code_start()

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
