import sys, traceback
import threading
import weakref
import traceback
from functools import partial
from ..cached_compile import cached_compile
from ..runtime_identifier import get_runtime_identifier
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
        inputs,
        outputs,
    ):
        assert "code_start" in inputs
        assert "code_stop" in inputs
        assert "code_update" in inputs

        self.parent = weakref.ref(parent)
        self.PINS = PINS()
        self.namespace = {}
        self.outputs = outputs
        self._pending_updates = 0
        self.inputs = inputs.copy()
        self.input_must_be_defined = {k for k,v in inputs.items() if v[2]}
        self._pending_inputs = {name for name in self.input_must_be_defined}
        self.values = {name: None for name in inputs.keys()}
        self.exception = None
        self.updated = set()
        self._running = False
        self._set_namespace()
        self._pending_updates = 0
        self._spontaneous = True

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


    def process_input(self, name, data):
        #print("process_input", self.parent(), name, self._pending_inputs)
        if self.parent() is None:
            return
        if self._destroyed:
            return

        self._pending_updates += 1

        mode, submode, _ = self.inputs[name]
        if mode == "buffer":
            #TODO: support silk, mixed, binary, cson submodes
            raise NotImplementedError

        assert mode == "ref" or submode in ("json", "text", None), (mode, submode)
        if submode == "pythoncode":
            identifier = str(self.parent()) + ":%s" % name
            if submode in ("buffer", "copy"):
                code = data
            else:
                code_obj = data
                code = code_obj.value
            code_object = cached_compile(code, identifier, "exec")
            value = code_object
        else:
            value = data

        # If we have missing values, and this input is currently default, it's no longer missing
        if value is not None:
            if self._pending_inputs and self.values[name] is None:
                self._pending_inputs.remove(name)
        else:
            self._pending_inputs.add(name)


        self.values[name] = value
        self.updated.add(name)
        updated_now = name

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
        exec(code_obj, self.namespace)

    def _code_start(self):
        #print("CODE-START", self.parent())
        assert threading.current_thread() is threading.main_thread()
        assert not self._running
        try:
            self._spontaneous = False
            self.namespace["IDENTIFIER"] = get_runtime_identifier(self.parent())
            self._execute(self.code_start_block)
            self._running = True
        finally:
            self._spontaneous = True
            p = self.parent()
            if p is not None:
                p.flush()


    def _code_update(self, updated):
        assert threading.current_thread() is threading.main_thread()
        if not self._running:
            return #kludge, no idea why it is necessary...
        #if not self._running:
        #    self._code_start() #kludge, no idea why it is necessary...
        try:
            self._spontaneous = False
            self._execute(self.code_update_block)
        finally:
            self._spontaneous = True
            p = self.parent()
            if p is not None:
                p.flush()


    def _code_stop(self):
        assert threading.current_thread() is threading.main_thread()
        if self._running:
            try:
                self._spontaneous = False
                self._execute(self.code_stop_block)
            finally:
                self._spontaneous = True
                self._running = False
                self._set_namespace()
                p = self.parent()
                if p is not None:
                    p.flush()


    def _set_namespace(self):
        keep = {k:v for k,v in self.namespace.items() if k.startswith("_")}
        self.namespace.clear()
        self.namespace.update(keep)
        self.namespace["PINS"] = self.PINS
        for name in self.values:
            v = self.values[name]
            mode, submode, _ = self.inputs[name]
            if name in self.outputs:
                assert mode != "signal"
                e = ReactorEdit(self, name)
            else:
                if mode == "signal":
                    e = ReactorInputSignal(self, name)
                else:
                    e = ReactorInput(self, name)
            setattr(self.PINS, name,  e)
            if v is not None and mode != "signal":
                value = v
                e.defined = True
                e._value = value
        for name in self.outputs:
            if name in self.values:
                continue
            mode, submode = self.outputs[name]
            if mode == "signal":
                e = ReactorOutputSignal(self, name)
            else:
                e = ReactorOutput(self, name)
            setattr(self.PINS, name,  e)


    def update(self, updated, *, force_start=False, updated_now = None):

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
            if self._running:
                self._code_stop()
                if "code_start" not in updated and not force_start:
                    self._code_start()
            self.code_update_block = self.values["code_update"]
            do_update = True

        # Update namespace of inputs
        for name in self.inputs.keys():
            #pin = self.namespace[name]
            pin = getattr(self.PINS, name)
            if name in updated:
                mode, submode, _ = self.inputs[name]
                value = self.values[name]
                if mode != "signal":
                    pin._value = value
                    pin.defined = True
                else:
                    pin.updated_now = False
                    v._clear = True
                    if name == updated_now:
                        pin.updated_now = True
                pin.updated = True
                do_update = True
            else:
                pin.updated_now = False
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


    def output_update(self, name, value, preliminary=False, priority=False):
        """Propagates a PINS.name.set in the reactor code"""
        p = self.parent()
        p.output_update(name, value, preliminary, priority, self._spontaneous)


    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        self._code_stop()
