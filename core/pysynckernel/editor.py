
import weakref
from ...dtypes.objects import PythonEditorCodeObject
from ...dtypes import data_type_to_data_object

class Editor:
    name = "editor"
    _destroyed = False

    class EditorInput:
        def __init__(self, parent, name):
            self._parent = weakref.ref(parent)
            self._name = name
            self._value = None
            self.updated = False
        def get(self):
            return self._value

    class EditorOutput:
        def __init__(self, parent, name):
            self._parent = weakref.ref(parent)
            self._name = name
        def set(self, value):
            p = self._parent()
            if p is None:
                return
            p.parent().output_update(self._name, value)

    class EditorEdit:
        def __init__(self, parent, name):
            self._parent = weakref.ref(parent)
            self._name = name
            self._value = None
            self.updated = False
        def get(self):
            return self._value
        def set(self, value):
            self._value = value
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
        inputs["code_start"] = PythonEditorCodeObject("code_start", ("text", "code", "python"))
        inputs["code_stop"] = PythonEditorCodeObject("code_stop", ("text", "code", "python"))
        inputs["code_update"] = PythonEditorCodeObject("code_update", ("text", "code", "python"))
        self.inputs = inputs
        self._pending_inputs = {name for name in inputs.keys()}
        self.values = {name: None for name in inputs.keys()}
        self.registrar_namespace = {}
        self.exception = None
        self.updated = set()
        self._active = False
        self._set_namespace()

    def process_input(self, name, data):

        if self.parent() is None:
            return

        if name == "@REGISTRAR":
            try:
                registrar_name, key, namespace_name = data
                context = self.parent().context
                registrars = context.registrar
                registrar = getattr(registrars, registrar_name)
                try:
                    registrar_value = registrar.get(key)
                except KeyError:
                    self._pending_inputs.add(namespace_name)
                self.namespace[namespace_name] = registrar_value
                self.registrar_namespace[namespace_name] = registrar_value
                if namespace_name in self._pending_inputs:
                    self._pending_inputs.remove(namespace_name)

                self._code_stop()
                self._active = False

                if not self._pending_inputs:
                    updated = set(self.inputs.keys()) #TODO: not for undefined optional inputs
                    self.update(updated)
                    self.updated = set()

            except Exception as exc:
                self.exception = exc
                import traceback
                traceback.print_exc()

            return

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

    def _execute(self, code_obj):
        exec(code_obj.code, self.namespace)
        if code_obj.func_name:
            exec("{0}()".format(code_obj.func_name), self.namespace)

    def _code_stop(self):
        if self._active:
            try:
                self._execute(self.code_stop_block)
            finally:
                self._active = False
            self._set_namespace()

    def _code_start(self):
        assert not self._active
        self._execute(self.code_start_block)
        self._active = True


    def _set_namespace(self):
        self.namespace.clear()
        for name in self.values:
            v = self.values[name]
            if name in self.output_names:
                e = self.EditorEdit(self, name)
            else:
                e = self.EditorInput(self, name)
            self.namespace[name] = e
            if v is not None:
                value = v.data
                e._value = value
        for name in self.output_names:
            if name in self.values:
                continue
            self.namespace[name] = self.EditorOutput(self, name)
        self.namespace.update(self.registrar_namespace)

    def update(self, updated):

        # If any code object is updated, recompile

        if "code_stop" in updated:
            self.code_stop_block = self.values["code_stop"]

        if "code_start" in updated:
            self._code_stop()
            self.code_start_block = self.values["code_start"]
            for name in self.inputs.keys():
                if name not in ("code_update", "code_stop"):
                    updated.add(name)
                    do_update = True

        do_update = False
        if "code_update" in updated:
            self._code_stop()
            self.code_update_block = self.values["code_update"]
            do_update = True

        # Update namespace of inputs
        for name in self.inputs.keys():
            if name in updated:
                self.namespace[name]._value = self.values[name].data
                self.namespace[name].updated = True
                do_update = True
            else:
                self.namespace[name].updated = False

        if "code_start" in updated:
            self._code_start()

        if do_update:
            self._execute(self.code_update_block)

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        self._code_stop()
