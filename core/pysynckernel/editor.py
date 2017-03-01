
import weakref
from ...dtypes.objects import PythonEditorCodeObject
from ...dtypes import data_type_to_data_object
from ..process import get_runtime_identifier
class PINS:
    pass

class Editor:
    name = "editor"
    _destroyed = False

    class EditorInput:
        def __init__(self, parent, dtype, name):
            self._parent = weakref.ref(parent)
            self._dtype = dtype
            self._name = name
            self._value = None
            self.updated = False
            self.defined = False
        def get(self):
            return self._value

    class EditorInputSignal:
        def __init__(self, parent, name):
            self._parent = weakref.ref(parent)
            self._name = name
            self.updated = False

    class EditorOutput:
        def __init__(self, parent, dtype, name):
            self._parent = weakref.ref(parent)
            self._dtype = dtype
            self._name = name
        def set(self, value):
            p = self._parent()
            if p is None:
                return
            p.output_update(self._name, value)

    class EditorOutputSignal:
        def __init__(self, parent, name):
            self._parent = weakref.ref(parent)
            self._name = name
        def set(self):
            p = self._parent()
            if p is None:
                return
            p.output_update(self._name, None)

    class EditorEdit:
        def __init__(self, parent, dtype, name):
            self._parent = weakref.ref(parent)
            self._dtype = dtype
            self._name = name
            self._value = None
            self.updated = False
            self.defined = False
        def get(self):
            return self._value
        def set(self, value):
            self._value = value
            self.defined = True
            p = self._parent()
            if p is None:
                return
            if p.values[self._name] is None:
                p.values[self._name] = p.inputs[self._name]
            p.values[self._name].data = value
            p.output_update(self._name, value)

    def __init__(self,
        parent,
        input_data,outputs
    ):
        assert "code_start" not in input_data
        assert "code_stop" not in input_data
        assert "code_update" not in input_data

        self.parent = weakref.ref(parent)
        self.PINS = PINS()
        self.namespace = {}
        self.input_data = input_data
        self.input_must_be_defined = {k for k,v in input_data.items() if v[1]}
        self.outputs = outputs


        inputs = {name: data_type_to_data_object(value[0])(name, value[0]) for name, value in input_data.items()}
        inputs["code_start"] = PythonEditorCodeObject("code_start", ("text", "code", "python"))
        inputs["code_stop"] = PythonEditorCodeObject("code_stop", ("text", "code", "python"))
        inputs["code_update"] = PythonEditorCodeObject("code_update", ("text", "code", "python"))
        self.inputs = inputs
        self._pending_inputs = {name for name in self.input_must_be_defined}\
          .union({"code_start", "code_update", "code_stop"})
        self.values = {name: None for name in inputs.keys()}
        self.registrar_namespace = {}
        self.exception = None
        self.updated = set()
        self._active = False
        self._spontaneous = True
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
                registrar_value = None
                try:
                    registrar_value = registrar.get(key)
                except KeyError:
                    self._pending_inputs.add(namespace_name)
                if self.registrar_namespace.get(namespace_name, None) == registrar_value:
                    return
                self.registrar_namespace[namespace_name] = registrar_value
                self.namespace[namespace_name] = registrar_value
                if registrar_value is not None and namespace_name in self._pending_inputs:
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
        if name in self._pending_inputs and self.values[name] is None:
            self._pending_inputs.remove(name)

        self.values[name] = data_object
        if name in self.registrar_namespace:
            self.registrar_namespace.remove(name)
        self.updated.add(name)

        # With all inputs now present, we can issue updates
        if not self._pending_inputs:
            self.update(self.updated)
            self.updated = set()

    def _execute(self, code_obj):
        exec(code_obj.code, self.namespace)
        if code_obj.func_name:
            exec("{0}()".format(code_obj.func_name), self.namespace)


    def _code_start(self):
        from ... import run_work
        assert not self._active
        try:
            self._spontaneous = True
            self.namespace["IDENTIFIER"] = get_runtime_identifier(self.parent())
            self._execute(self.code_start_block)
        finally:
            self._spontaneous = False
            run_work()
        self._active = True

    def _code_update(self):
        from ... import run_work
        assert self._active
        try:
            self._spontaneous = True
            self._execute(self.code_update_block)
        finally:
            self._spontaneous = False
            run_work()

    def _code_stop(self):
        from ... import run_work
        if self._active:
            self._spontaneous = False
            try:
                self._execute(self.code_stop_block)
            finally:
                self._active = False
                self._spontaneous = True
                self._set_namespace()
                run_work()

    def _set_namespace(self):
        #self.namespace.clear() #need to keep ipython vars
        dels = [k for k in self.namespace if not k.startswith("_")]
        for k in dels:
            self.namespace.pop(k)
        self.namespace["PINS"] = self.PINS
        for name in self.values:
            v = self.values[name]
            dtype = self.inputs[name].data_type
            if name in self.outputs:
                assert dtype != "signal"
                e = self.EditorEdit(self, dtype, name)
            else:
                if dtype == "signal":
                    e = self.EditorInputSignal(self, name)
                else:
                    e = self.EditorInput(self, dtype, name)
            setattr(self.PINS, name,  e)
            #self.namespace[name] = e
            if v is not None and dtype != "signal":
                value = v.data
                e.defined = True
                e._value = value
        for name in self.outputs:
            if name in self.values:
                continue
            dtype = self.outputs[name]
            if dtype == "signal":
                e = self.EditorOutputSignal(self, name)
            else:
                e = self.EditorOutput(self, dtype, name)
            #self.namespace[name] = e
            setattr(self.PINS, name,  e)

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
                    if self.values[name] is not None:
                        updated.add(name)
                        do_update = True

        do_update = False
        if "code_update" in updated:
            #self._code_stop() #why? if so, we should restart...
            self.code_update_block = self.values["code_update"]
            do_update = True

        # Update namespace of inputs
        for name in self.inputs.keys():
            #pin = self.namespace[name]
            pin = getattr(self.PINS, name)
            if name in updated and name not in self.registrar_namespace:
                v = self.values[name]
                if v.data_type != "signal":
                    pin._value = v.data
                    pin.defined = True
                pin.updated = True
                do_update = True
            else:
                pin.updated = False

        if "code_start" in updated:
            self._code_start()

        if do_update:
            self._code_update()

    def output_update(self, name, value):
        self.parent().output_update(name, value)
        if self._spontaneous:
            import seamless
            seamless.run_work()

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        self._code_stop()
