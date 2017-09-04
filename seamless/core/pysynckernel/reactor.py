import sys, traceback
import threading
import weakref
from functools import partial
from ...dtypes.objects import PythonReactorCodeObject
from ...dtypes import data_type_to_data_object
from ..worker import get_runtime_identifier
from .reactor_pins import ReactorInput, ReactorInputSignal, \
    ReactorOutput, ReactorOutputSignal, ReactorEdit

class PINS:
    pass

class Reactor:
    name = "reactor"
    _destroyed = False
    _active = False

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
        self._pending_updates = 0


        inputs = {name: data_type_to_data_object(value[0])(name, value[0]) for name, value in input_data.items()}
        inputs["code_start"] = PythonReactorCodeObject("code_start", ("text", "code", "python"))
        inputs["code_stop"] = PythonReactorCodeObject("code_stop", ("text", "code", "python"))
        inputs["code_update"] = PythonReactorCodeObject("code_update", ("text", "code", "python"))
        self.inputs = inputs
        self._pending_inputs = {name for name in self.input_must_be_defined}\
          .union({"code_start", "code_update", "code_stop"})
        self.values = {name: None for name in inputs.keys()}
        self.registrar_namespace = {}
        self.exception = None
        self.updated = set()
        self._running = False
        self._spontaneous = True
        self._set_namespace()
        self._pending_updates = 0

        from ..macro import add_activate
        add_activate(self)

    def _update_from_start(self):
        for up in self.inputs.keys():
            if up not in self.input_must_be_defined:
                continue
            self.updated.add(up)
        updated = set(self.updated)
        self.updated.clear()
        self.update(updated, force_start=True)

    def activate(self):
        if self._active:
            return
        if not self._pending_inputs:
            self._update_from_start()
        self._active = True

    def process_input(self, name, data, resource_name):
        #print("process_input", self.parent(), name, self._pending_inputs)
        if self.parent() is None:
            return
        if self._destroyed:
            return

        self._pending_updates += 1
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
                self._running = False

                if self._active and not self._pending_inputs:
                    self._update_from_start()

            except Exception as exc:
                self.exception = exc, sys.exc_info()[2]
                traceback.print_exc()

            updates_processed = self._pending_updates
            self._pending_updates = 0
            p = self.parent()
            if p is not None:
                p.updates_processed(updates_processed)

            return

        data_object = self.inputs[name]
        # instance of datatypes.objects.DataObject

        try:
            data_object.parse(data, resource_name)
            data_object.validate()

        except Exception as exc:
            self.exception = exc, sys.exc_info()[2]
            traceback.print_exc()
            return

        # If we have missing values, and this input is currently default, it's no longer missing
        if name in self._pending_inputs and self.values[name] is None:
            self._pending_inputs.remove(name)

        self.values[name] = data_object
        if name in self.registrar_namespace:
            self.registrar_namespace.remove(name)
        self.updated.add(name)

        updates_processed = self._pending_updates

        # With all inputs now present, we can issue updates
        if self._active and not self._pending_inputs:
            updated = set(self.updated)
            self.updated.clear()

            try:
                self.update(updated, updated_now=updated_now)
            except Exception as exc:
                self.exception = exc, sys.exc_info()[2]
                traceback.print_exc()
            else:
                self.exception = None

        self._pending_updates -= updates_processed
        p = self.parent()
        if p is not None:
            p.updates_processed(updates_processed)

    def _execute(self, code_obj):
        exec(code_obj.code, self.namespace)
        if code_obj.func_name:
            exec("{0}()".format(code_obj.func_name), self.namespace)


    def _code_start(self):
        #print("CODE-START", self.parent())
        assert threading.current_thread() is threading.main_thread()
        from ... import run_work
        assert not self._running
        try:
            self._spontaneous = True
            self.namespace["IDENTIFIER"] = get_runtime_identifier(self.parent())
            self._execute(self.code_start_block)
            self._running = True
        finally:
            self._spontaneous = False
            run_work()

    def _code_update(self, updated):
        assert threading.current_thread() is threading.main_thread()
        from ... import run_work
        if not self._running:
            return #kludge, no idea why it is necessary...
        #if not self._running:
        #    self._code_start() #kludge, no idea why it is necessary...
        try:
            self._spontaneous = True
            self._execute(self.code_update_block)
        finally:
            self._spontaneous = False
            run_work()

    def _code_stop(self):
        assert threading.current_thread() is threading.main_thread()
        from ... import run_work
        if self._running:
            self._spontaneous = False
            try:
                self._execute(self.code_stop_block)
            finally:
                self._running = False
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
                e = ReactorEdit(self, dtype, name)
            else:
                if dtype == "signal":
                    e = ReactorInputSignal(self, name)
                else:
                    e = ReactorInput(self, dtype, name)
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
                e = ReactorOutputSignal(self, name)
            else:
                e = ReactorOutput(self, dtype, name)
            #self.namespace[name] = e
            setattr(self.PINS, name,  e)

        self.namespace.update(self.registrar_namespace)

    def update(self, updated, force_start=False):

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
                    pin._store = v.store
                else:
                    v._clear = True
                pin.updated = True
                do_update = True
            else:
                pin.updated = False

        if "code_start" in updated or force_start:
            self._code_start()

        if do_update or force_start:
            self._code_update(updated)

        for name in self.inputs.keys():
            pin = getattr(self.PINS, name)
            if isinstance(pin, ReactorInputSignal) and pin._clear == False:
                updated.add(name)
                pin._clear = True

    def output_update(self, name, value):
        """Propagates a PINS.name.set in the reactor code to the seamless manager"""
        import seamless
        p = self.parent()
        run_work = self._spontaneous

        # Normally, reactor code runs in the main thread, but not necessarily:
        # the reactor code may launch its own threads!!
        if p is not None:
            if threading.current_thread() is threading.main_thread():
                p.output_update(name, value)
            else:
                f = partial(p.output_update, name, value)
                seamless.add_work(f,priority=True)
                run_work = True
        if run_work:
            seamless.run_work()

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        self._code_stop()
